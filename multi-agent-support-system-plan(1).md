# Multi-Agent Customer Support System — Development Plan

## 0. Design Philosophy (confirmed)

- **Orchestrator-worker pattern**: one root/supervisor agent holds task context and conversation state. Subagents are **stateless tools** — they receive a scoped input, do one job, return a structured result, and forget everything.
- **Centralized routing**: all inter-agent communication passes through the root. Subagents never talk to each other directly. This keeps the system debuggable and prevents emergent routing chaos.
- **Independent scaffolds**: each subagent is built and testable in isolation (own repo folder, own eval suite, own prompt) before being wired into the root graph as a callable tool.
- **Model-agnostic harness**: the "brain" (root and every subagent) is swappable per-agent, not just globally — e.g. root on a strong hosted model, a classification subagent on a small local model via Ollama.

The main risk you named — one agent doing too much / job oversimplification — is mitigated by treating **subagent scope definition** as a first-class design artifact (see §2), not something that emerges from code.

---

## 1. High-Level Architecture

```
                         ┌─────────────────────┐
                         │   Root/Orchestrator  │
                         │   Agent (LangGraph)  │
                         │  - owns conversation │
                         │    state & thread    │
                         │  - long-term memory  │
                         │    read/write        │
                         │  - guardrail gate     │
                         │  - HITL interrupts    │
                         └──────────┬───────────┘
                                    │ tool calls (structured I/O)
        ┌───────────────┬──────────┼──────────┬───────────────┐
        ▼               ▼          ▼          ▼               ▼
   ┌─────────┐    ┌──────────┐ ┌────────┐ ┌─────────┐   ┌───────────┐
   │ Intent/ │    │ Retrieval│ │ Ticket │ │ Actions │   │ Escalation│
   │ Router  │    │ (RAG)    │ │ /CRM   │ │ (order  │   │ / HITL    │
   │ Agent   │    │ Agent    │ │ Agent  │ │ refund, │   │ Agent     │
   └─────────┘    └────┬─────┘ └────────┘ │ etc.)   │   └───────────┘
                        │                  └─────────┘
                        ▼
                  ┌───────────────┐
                  │  PostgreSQL   │
                  │  + pgvector   │
                  │  (checkpoints,│
                  │  store, RAG,  │
                  │  approvals)   │
                  └───────────────┘
```

**Note on the single-Postgres decision**: checkpointer, long-term memory store, RAG vectors, and the HITL approval queue all live in the same Postgres instance (separate schemas/tables, not one undifferentiated blob — see §3.2–3.4, §3.6). This was a deliberate consolidation: one service to run and back up instead of Postgres + a separate vector DB + a separate approval store, which directly serves the self-contained/OSS goal in §4.

Each subagent is itself a small LangGraph graph (or even a single node) compiled and exposed to the root as a `@tool`-wrapped function with a strict Pydantic input/output schema. From the root's perspective, a subagent IS a tool — this is what lets you build them independently.

---

## 2. Subagent Contract (do this before writing any subagent)

For every subagent, write a one-page spec before code:

| Field | Description |
|---|---|
| **Name** | e.g. `retrieval_agent` |
| **Single responsibility** | One sentence. If it needs "and", split it. |
| **Input schema** | Pydantic model — what the root sends it |
| **Output schema** | Pydantic model — structured, never free text only |
| **Allowed tools** | What external tools/APIs this subagent itself can call |
| **Memory access** | None / read-only long-term memory / read-write (rare) |
| **Model tier** | Which model class it needs (reasoning-heavy vs. cheap/fast) |
| **Failure mode** | What it returns when it can't complete the task (never silent failure) |
| **Eval dataset** | Where its golden test cases live |

Suggested initial subagent set for support, expanded below (§2.1–2.5):
1. **Router/Intent Agent** — classifies query type + urgency, cheap/fast model
2. **Retrieval (RAG) Agent** — knowledge base search + synthesis
3. **Ticket/CRM Agent** — reads/writes ticket & customer records
4. **Action Agent** — executes side-effecting operations (refunds, order changes) — always behind HITL gate
5. **Escalation Agent** — formats handoff package for a human agent

Keep this list in a shared `subagent_registry.yaml` so the root's tool list is generated, not hand-maintained.

### 2.1 Router/Intent Agent

**Job**: first-pass triage of an incoming message — intent category, urgency, and enough signal for root to decide which subagent(s) to call next. This is *not* the agent that decides what to do about the message; it just labels it.

- **Input**: latest customer message + minimal recent context (not full history)
- **Output**: structured — `{intent: enum, urgency: enum, confidence: float, requires_human: bool}`
- **Model tier**: cheapest viable option. This is the strongest candidate in the whole system for a non-LLM or small-local-model approach — embedding similarity against known intent categories, a fine-tuned classifier, or a small local model (e.g. your Ollama qwen3:4b setup) can often do this at a fraction of the cost of calling it with a frontier model.
- **Failure mode**: low confidence → `requires_human: true` or a generic "needs clarification" intent, never a silent guess. Root should be able to trust the confidence score to decide whether to trust the routing or ask a clarifying question itself.
- **Scoping risk**: don't let this agent creep into answering the question or deciding actions — that's job-mixing. Its only output is a label.

### 2.2 Retrieval (RAG) Agent

**Job**: given a customer question, retrieve relevant knowledge (help docs, policy, past resolved tickets) and synthesize a grounded, cited answer — not raw chunks.

- **Input**: the question, plus any filters root can supply (product line, customer segment) to narrow search
- **Output**: structured — `{answer: str, sources: list[Citation], confidence: float}`
- **Model tier**: mid-tier. Retrieval itself (embedding + Qdrant search) is cheap; the synthesis step is the expensive part and benefits from a capable model since it needs to avoid hallucinating beyond what was retrieved.
- **Failure mode**: if retrieved chunks don't actually answer the question, it should say so (`confidence: low`, `answer: None`) rather than generating a plausible-sounding but ungrounded answer. This is a common failure point worth a dedicated eval set (§3.8).
- **Note**: this agent owns the hybrid search + rerank step described in §3.3 — root never talks to Postgres/pgvector directly.

### 2.3 Ticket/CRM Agent

**Job**: the single point of contact for structured customer/account data — reading ticket history, account tier, order records, and writing new ticket entries or updates. Centralizing this here (rather than letting multiple subagents touch the CRM) keeps write access auditable and consistent.

- **Input**: customer/account ID + the specific operation requested (`get_history`, `create_ticket`, `update_ticket`, `get_order`)
- **Output**: structured record data, or a confirmation of a write with the resulting record ID
- **Model tier**: can often be low/no-LLM for read operations (a thin API wrapper exposed as a tool) — reserve model calls for cases where the agent needs to interpret an ambiguous request into a structured CRM query. Don't pay for an LLM call to do a straightforward API lookup.
- **Failure mode**: record not found / permission denied returned as explicit structured error, not an assumed default.
- **Memory access note**: this is the agent most likely to also read/write long-term memory (§3.2) alongside the CRM system itself — worth deciding whether "customer profile in long-term store" and "CRM record" are the same source of truth or two systems this agent reconciles.

### 2.4 Action Agent

**Job**: the only subagent permitted to execute side-effecting operations — refunds, subscription changes, order modifications, account changes. Everything here is high-stakes by definition, which is why it's split out rather than folded into the Ticket/CRM agent (which is read/write on *records*, not on money or irreversible state).

- **Input**: the specific action + parameters, already validated by root/guardrails as within policy shape (e.g. refund amount under the agent's own hard cap)
- **Output**: `{status: success/failed/pending_approval, action_id, details}`
- **Model tier**: doesn't need a large model to execute a well-defined action — the risk here isn't reasoning quality, it's authorization. Keep the model's job narrow (map validated intent → correct API call) and put the real safety burden on guardrails + HITL, not on prompting the model to "be careful."
- **HITL gate**: this is the agent from §3.6 whose actions above a threshold always route through `interrupt()`. Every action this agent takes should be logged with full parameters for audit, regardless of whether it was human-approved or auto-approved under threshold.
- **Failure mode**: any ambiguity in parameters (e.g. "which order?") should bounce back to root for clarification rather than the Action Agent guessing — this agent should never infer intent, only execute already-confirmed intent.

### 2.5 Escalation Agent

**Job**: root decides *when* a conversation needs a human (low confidence, explicit request, guardrail flag, blocked action); this agent decides *how* to package that handoff well. It is a synthesis/formatting specialist, not a decision-maker.

- **Input**: full conversation transcript + any context root has gathered (CRM lookups, retrieval results, attempted actions)
- **Output**: `{summary: str, urgency: enum, suggested_team: enum, structured_ticket_fields: dict}`
- **Responsibilities**: condense the conversation into something a human can scan in seconds (not re-read), pull relevant account context, classify urgency for queue prioritization, route to the right team, and format into whatever your ticketing system's API expects.
- **Model tier**: mid-tier — summarization quality matters (a bad handoff wastes the human's time and undoes any goodwill built during the automated part of the conversation), but it doesn't need frontier-model reasoning.
- **Scoping note**: if your handoff format is simple (transcript + template, no real synthesis needed), this doesn't need to be an LLM agent at all — a deterministic formatter is cheaper and more predictable. Only make it a model-backed subagent if summarization/routing genuinely requires judgment.
- **Eval focus**: "would a human rep find this handoff immediately useful?" is a good eval question — track it separately from the rest of the system's task-success metrics.

---

## 3. The Eight Subsystems

### 3.1 State / Short-Term Memory
- Use LangGraph's `StateGraph` with a typed `TypedDict`/Pydantic state: conversation messages, current customer context, active subtask, guardrail flags.
- **Checkpointer**: start with `MemorySaver` for dev, move to `langgraph-checkpoint-sqlite` for single-instance, then `langgraph-checkpoint-postgres` for production (multi-instance, durable). You're already on this path in Autonomi — reuse that checkpointer setup here.
- Thread ID = conversation/session ID. Subagents receive a **scoped slice** of state (only what they need), never the full state object — this is what keeps them stateless and swappable.

### 3.2 Persistent / Long-Term Memory
- Use LangGraph's `Store` API (`BaseStore` → `PostgresStore`, `langgraph-checkpoint-postgres` ships one) for cross-session memory: customer profile facts, past resolved issues, preferences.
- Namespace by customer ID. Write access restricted to root (and maybe the CRM subagent) — subagents should not silently mutate long-term memory.
- **Decided**: long-term memory and RAG both live in Postgres now (§3.3–3.4), but as **separate tables/schemas**, not the same rows — long-term memory is structured/keyed facts, RAG is unstructured document retrieval with embeddings. Same database instance, different concerns. Don't conflate them just because they share infrastructure.

### 3.3 RAG System
- Ingestion pipeline: source docs (help center articles, policy docs, past resolved tickets) → chunk → embed → upsert into a Postgres table with a `vector` column (pgvector).
- Chunking strategy: semantic/recursive chunking (400–800 tokens, with overlap) rather than fixed-size for policy documents.
- Retrieval: hybrid search — dense similarity via pgvector (`<=>` cosine or `<#>` inner product operator, HNSW index) combined with Postgres full-text search (`tsvector`/`ts_rank`, standing in for the sparse/BM25 side) — plus metadata filtering (product line, doc freshness date) via normal `WHERE` clauses, and a reranking step (cross-encoder or LLM-based rerank) before synthesis.
- The Retrieval Agent's job is retrieval **and** synthesis into a structured answer + citations — never hand raw chunks back to the root.
- **Trade-off worth knowing**: pgvector's hybrid search is real but less turnkey than a purpose-built vector DB like Qdrant (you're combining two Postgres features yourself rather than one native hybrid API). At support-system scale this is a fine trade for the operational simplicity of one database — revisit only if retrieval latency/quality becomes a measured problem, not preemptively.

### 3.4 Vector Storage (pgvector)
- Single Postgres instance (same one holding checkpoints and long-term memory), `pgvector` extension enabled. Consolidating here directly serves the self-contained/OSS goal in §4 — one database to run, back up, and ship to a buyer instead of Postgres + a separate vector service.
- Table design mirrors the old collection-per-type idea, just as tables instead of collections:
  - `kb_articles` — help center content
  - `resolved_tickets` — past resolutions (useful for retrieval-augmented troubleshooting)
  - Keep them separate rather than one giant table with a `type` column — keeps embedding dimension/model choices decoupled if you ever need different embedding models per content type, and keeps indexes smaller/faster.
- Use an HNSW index (`pgvector` ≥0.5) for approximate nearest-neighbor search at this scale over IVFFlat — better recall/speed trade-off and no need to retrain the index as data grows.
- Standard B-tree/composite indexes on filter columns (product, category, date) alongside the vector index so filtered search stays fast as the table grows.
- **Embedding model**: for the self-contained goal (§4), prefer a strong open-source embedding model you can run locally (e.g. BGE, Nomic Embed, or similar sentence-transformer models) over a paid embedding API — keeps ingestion cost at zero and avoids another external dependency. Worth a small eval to confirm retrieval quality is acceptable before committing.

### 3.5 Guardrails / Validation — Hybrid Approach

Combine hand-rolled checks with open-source guardrail libraries rather than choosing one or the other — use whichever is the right tool for each specific check:

- **Hand-rolled** (fast, cheap, fully transparent — use for anything deterministic or business-specific):
  - Pydantic schema validation on every structured subagent output (reject and retry on malformed)
  - Business policy checks (refund caps, discount limits) — these are your rules, no library needed
  - Simple regex/pattern checks where they're reliable enough (obvious PII patterns, profanity lists)
- **Library-based** (use for checks that need broader pattern coverage than you want to hand-maintain):
  - PII detection — Microsoft **Presidio** (OSS) is a solid fit, handles far more PII patterns/entities than a hand-rolled regex set
  - Prompt-injection / jailbreak screening on retrieved RAG content and user input — **NeMo Guardrails** or **Guardrails AI**'s core library (both OSS) for this class of check, since injection patterns evolve and are hard to hand-maintain reliably
  - Toxicity/tone checks on outbound customer-facing text where a hand-rolled check would be too brittle
- Two layers regardless of which approach handles a given check:
  - **Input guardrails** (before root routes): PII redaction, prompt-injection screening, abuse detection
  - **Output guardrails** (before anything reaches the customer or an external system): schema validation, policy compliance, tone/safety
- Implement as **graph nodes**, not afterthoughts — a `validate_output` node the root always routes through before `END`. Log every guardrail decision (pass/fail/which check) as a trace event (§3.7) — this becomes your red-teaming eval data later (§3.8).

### 3.6 Human-in-the-Loop / Checkpoints

**Flow**: `Agent → Checkpoint → Approval → Resume`

- Use LangGraph's `interrupt()` for durable HITL — pauses execution, persists state via the Postgres checkpointer, and the graph does **not** continue running in the background while waiting; it truly suspends until a resume signal arrives. This matches your requirement exactly — `interrupt()` is the correct primitive over polling or a background retry loop.
- **Approval states** (explicit enum, drives both backend logic and the UI):
  - `pending` — waiting for human review
  - `approved` — resume workflow from the interrupt point
  - `rejected` — stop the current plan or trigger re-planning (root decides which, based on rejection reason)
  - `expired` — no response within SLA window. **Default behavior: auto-escalate** (an unreviewed HITL request implies real stakes — if it turns out not to be worth acting on, a human reviewer discards it downstream rather than the system silently dropping something that mattered). This default should still be **configurable per breakpoint type** rather than hardcoded, so a genuinely low-stakes breakpoint can be set to auto-reject instead if that's ever the better default for it.
  - `cancelled` — request withdrawn (e.g. customer resolved the issue another way before approval came through)
- **Cross-agent isolation — enforced at the data layer, not the LLM**: Agent A must never see or infer Agent B's pending approval requests. Implement this with Postgres **Row-Level Security (RLS)** policies on the approvals table (scoped by agent/session/reviewer role) rather than trusting a prompt instruction — this is exactly the right call, since "don't look at that" is not a security boundary when it's just text in a system prompt. RBAC on top for which *human reviewers* can see/act on which approval categories (e.g. only finance-authorized reviewers see refund approvals above a threshold).
- **Breakpoint triggers** (unchanged from before, now feeding the state machine above):
  - Action Agent about to execute a refund/action above a threshold
  - Guardrail flags low-confidence or policy-ambiguous response
  - Customer explicitly requests a human
  - Router confidence below threshold
- **UX additions for the internal approval tool**:
  - **Risk badges** — visual severity indicator per request (derived from action type + amount/impact, not just a raw LLM confidence score) so reviewers triage at a glance
  - **SLA timer** — visible countdown to the `expired` transition, so reviewers see urgency without checking timestamps manually
- Since this is your own internal tool (not a SaaS approval product), build it as a small self-hosted app against the same Postgres instance — this keeps it inside the self-contained/OSS stack from §4 rather than adding another external dependency.

### 3.7 Observability & Tracing
- **Decided**: Langfuse (OSS, self-hostable) — chosen over LangSmith specifically to reduce service management overhead and cost, and to keep the self-contained/OSS goal (§4) intact for both you and your buyers. It has native LangChain/LangGraph callback and OTel integration, so wiring it up is nearly as direct as LangSmith would have been.
- Runs in the same `docker-compose.yml` as everything else (§4) — no external account/subscription required for buyers, and you're not centralizing all buyers' traces through a third-party SaaS account either.
- Minimum you want from day one: trace ID per conversation, span per subagent call with input/output, guardrail decisions logged as events (§3.5), HITL interrupts logged with resolution (§3.6).

### 3.8 Evaluation
- **Per-subagent eval**: each subagent's `subagent_registry` entry points to its own golden dataset + eval script (e.g. does the Router agent classify correctly, does Retrieval return the right doc). Run in CI on every change to that subagent.
- **End-to-end eval**: full conversation traces against expected outcomes (task success, guardrail correctness, escalation correctness). Langfuse has its own evaluation/scoring features that pair with the tracing you're already capturing, or a custom harness using your existing eval-design experience (you've already done O*NET-aligned scenario/eval design work — that instinct applies directly here).
- **Regression gate**: no subagent ships without its eval suite passing; track eval scores over time per subagent, not just system-wide.

### 3.9 Model Harness ("the Brain")
- Wrap model selection behind LangChain's `init_chat_model` (supports provider switching by string) or a thin custom factory — config-driven, one YAML/env entry per agent: `root: anthropic:claude-...`, `router: ollama:qwen3:4b`, etc.
- For local models: keep your existing Ollama setup from Autonomi; make sure the harness handles models with weaker tool-calling reliability gracefully (retry/repair loop on malformed tool calls — ties into guardrails §3.5).
- Config should let a user swap models without touching subagent code — this is the "harness" promise. Keep prompts and model-specific tuning (e.g. system prompt tweaks for weaker local models) in per-agent config, not hardcoded.

---

## 4. Self-Contained / Open-Source Stack

Goal: a buyer can run the whole system with a `docker-compose up` and their own model API key (or a fully local model), without needing to sign up for N separate SaaS subscriptions to get a working system. Not every piece can be zero-dependency (you still need *a* model provider unless running fully local), but the infrastructure layer should be.

| Component | Choice | Status |
|---|---|---|
| Orchestration | LangGraph | OSS ✓ |
| Backend / API | FastAPI | OSS ✓ |
| Caching / queues | Redis | OSS, self-hosted ✓ |
| State checkpoints | PostgreSQL (`langgraph-checkpoint-postgres`) | OSS, self-hosted ✓ |
| Long-term memory store | PostgreSQL (`Store` API) | OSS, self-hosted ✓ |
| Vector storage / RAG | PostgreSQL + `pgvector` | OSS, self-hosted ✓ |
| Embeddings | Local OSS model (candidates TBD — see §3.4) | OSS, self-hosted ✓ (avoids a paid embedding API) |
| Guardrails | Hand-rolled + Presidio + NeMo Guardrails / Guardrails AI core | OSS ✓ |
| HITL approval tool | Custom-built internal app (backend: FastAPI; frontend: Next.js or React, TBD) on the same Postgres | Self-hosted, no subscription ✓ |
| LLM (root + subagents) | Swappable via harness — hosted API (Anthropic/OpenAI/etc.) or fully local via Ollama | Buyer's choice — local path is zero-subscription ✓ |
| Observability | Langfuse (OSS, self-hosted) | OSS ✓ — decided over LangSmith to cut service management and cost |

**Backend/frontend stack (decided)**: FastAPI serves the frontend(s) and internal APIs; Redis handles caching and queues (a good fit for things like the semantic answer cache from §5.7 and any background job needs around ingestion or notifications). Frontend framework for the approval UI (Next.js vs. React) is still open — see §8.

No remaining stack conflicts against the self-contained/OSS goal — Langfuse closes the one gap that existed with LangSmith.

**Packaging implication**: since everything above other than the LLM itself is either OSS-self-hosted or embedded in your own code, the whole non-LLM stack should fit in one `docker-compose.yml` (Postgres+pgvector, Redis, the FastAPI backend, the approval app, Langfuse) — this becomes the actual deliverable for "self-contained" rather than just a design principle.

---

## 5. Cost & Token Efficiency

Your architecture is inherently n+1: root's own reasoning call plus a call per subagent invoked. Left unmanaged, that compounds fast across turns. Design for it now rather than patching later.

**1. Don't fan out to every subagent every turn.**
Root should call only the subagents the current turn actually needs — conditional routing based on the Router agent's output, not "always ask Retrieval and Ticket and Router." This is the single biggest lever.

**2. Use parallel tool-calling, not sequential single-tool decisions.**
If root needs both Retrieval and Ticket data for one turn, it should emit both tool calls in a single LLM response rather than: call → get result → decide → call again. LangGraph supports this pattern — collapse several round-trips into one root call + parallel subagent calls + one synthesis call.

**3. Right-size the model per subagent (you already have the harness for this).**
Router/classification is the clearest candidate for a small local model or even a non-LLM classifier (§2.1) — reserve expensive models for subagents where reasoning quality genuinely matters (Retrieval synthesis, Escalation summarization).

**4. Prompt caching.**
Subagent system prompts are largely static and reused constantly within and across conversations. Anthropic and other providers support prompt caching for exactly this — build it into the model harness from day one rather than retrofitting it.

**5. Scope context tightly per subagent call.**
Subagents are stateless, so root has to hand them context each time — cost isn't just number of calls, it's tokens per call. Passing full conversation history into every subagent invocation instead of a scoped, relevant slice is a quiet multiplier. Each subagent's input schema (§2) should define the *minimum* it needs.

**6. Cap and cheapen guardrail retry loops.**
Output-validation retries (§3.5) add calls on top of the base n+1. Set a hard retry cap, and use a cheap/fast model for the validator itself — it doesn't need the same model that generated the output.

**7. Cache common answers.**
For FAQ-shaped queries, a semantic cache (Redis is a natural fit here) in front of the Retrieval Agent's synthesis step can skip the LLM call entirely for repeat questions — check cache before hitting pgvector + synthesis.

**8. Instrument cost per node, not just latency.**
Tag traces (§3.7) with token usage per subagent call so you can see which subagent is actually expensive and target it specifically, rather than optimizing blind. Track cost-per-conversation as a first-class metric alongside task success in your eval suite (§3.8).

---

## 6. Suggested Repo Structure
```
support-system/
├── root_agent/                # orchestrator graph — owns classification, routing, synthesis
│   ├── graph.py
│   ├── state.py
│   ├── router.py               # inline classification/routing logic — NOT a subagent call
│   ├── guardrails/
│   └── prompts/
├── subagents/
│   ├── retrieval_agent/        # FAQ / RAG
│   │   ├── graph.py
│   │   ├── schema.py           # input/output Pydantic models
│   │   ├── eval/
│   │   └── README.md           # the subagent contract from §2
│   ├── action_agent/           # account/order actions
│   │   ├── graph.py
│   │   ├── schema.py
│   │   ├── eval/
│   │   └── README.md
│   └── escalation_agent/       # HITL handoff + ticket creation/tracking
│       ├── graph.py
│       ├── schema.py
│       ├── eval/
│       └── README.md
├── backend/                     # FastAPI app serving the frontend(s)
│   ├── api/
│   ├── cache.py                 # Redis caching
│   └── queues.py                # Redis-backed queues
├── memory/
│   ├── checkpointer.py         # Postgres checkpointer
│   └── store.py                # Postgres long-term memory store
├── rag/
│   ├── ingestion/
│   └── pgvector_client.py
├── guardrails/
│   ├── handrolled/              # schema + policy checks
│   └── library/                 # Presidio / NeMo Guardrails wrappers
├── approvals/                    # internal HITL approval app
│   ├── app/
│   ├── rls_policies.sql          # row-level security for cross-agent isolation
│   └── models.py                 # approval state machine
├── harness/
│   └── model_factory.py
├── observability/
│   └── tracing.py                # Langfuse
├── subagent_registry.yaml
├── docker-compose.yml            # postgres+pgvector, redis, fastapi backend, approvals app, langfuse
└── evals/
    └── e2e/
```

---

## 7. Phased Build Roadmap

**Phase 0 — Scaffolding**
- Repo structure, docker-compose for Postgres + pgvector, model harness with 1 hosted + 1 local model swappable, base checkpointer against Postgres from the start (no separate SQLite step needed now that Postgres is the day-one choice).

**Phase 1 — Single subagent, end-to-end**
- Build Retrieval Agent standalone with its own eval set. Prove ingestion → pgvector → retrieval → synthesis works in isolation.

**Phase 2 — Root + first subagent wired**
- Root graph with 1 tool (Retrieval Agent), thread-scoped state, basic guardrail (output schema validation), Langfuse tracing on. Wire root for parallel tool-calling (§4.2) from the start — retrofitting this after Phase 3 adds more subagents is harder than building it in now.

**Phase 3 — Expand subagents**
- Add Router, Ticket/CRM agents. Each built standalone first, then wired. Long-term memory store comes online here (customer context needed for Ticket agent).

**Phase 4 — Sensitive actions**
- Action Agent + HITL interrupts for anything side-effecting. Build the approval app (state machine, RLS policies, risk badges, SLA timer) here — this is the heaviest phase given the isolation and UX requirements from §3.6.

**Phase 5 — Evaluation & hardening**
- Full e2e eval suite, guardrail red-teaming (prompt injection via retrieved docs, jailbreak attempts), load testing on pgvector tables at realistic data volumes.

**Phase 6 — Escalation & polish**
- Escalation Agent, human handoff UX, observability dashboards, cost/latency tuning per subagent (right-sizing which subagents get expensive vs. cheap models).

**Phase 7 — Packaging for distribution**
- Consolidate the full OSS stack (§4) into a single `docker-compose.yml`, document buyer-side setup (bring-your-own model key or fully local), and verify the system runs with zero external subscriptions beyond the buyer's chosen LLM.

---

## 8. Open Decisions to Nail Down Next

1. **Embedding model**: which OSS local embedding model — needs a small retrieval-quality eval before committing (§3.4). See the walkthrough below.
2. **Approval app frontend**: Next.js vs. React (backend is decided: FastAPI) — TBD.
3. **RLS policy design**: exact scoping rules for which reviewer roles see which approval categories (§3.6) — needs your actual team/role structure to finalize.
