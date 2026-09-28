# Agent Architecture

The system uses a hierarchical, multi-agent pattern orchestrated via LangGraph.
State is persisted to PostgreSQL, enabling agents to be paused and resumed across worker boundaries.

## 1. `root_agent` (The Orchestrator)
- **Purpose**: Primary entry point for all conversation turns. Runs a ReAct loop, routes to subagents as tools, and synthesises final responses.
- **Input/Output**: `{ messages, session_id, user_id }` → updated `messages` array with the final reply.
- **Model**: Swappable via `agent_config` in the run config, built by `harness/model_factory.py`. The active provider and model are fetched from the `workspace_agent_config` table per request.
- **Tools**: Calls `retrieval_agent`, `action_agent`, and `escalation_agent` as LangChain tools.
- **Surprising/Non-obvious behavior**:
  - Contains a hardcoded `guardrail_check` node that inspects pending tool calls **before** they execute. If the LLM requests an `action_agent` call with `HIGH` or `CRITICAL` risk, the guardrail intercepts it, overrides the tool call to `escalation_agent`, and forces a HITL approval flow — without the LLM's knowledge.

## 2. `action_agent` (Order/Account Operations)
- **Purpose**: Executes mutating and read-only operations against external systems via the MCP layer.
- **Input/Output**: `ActionRequest` → `ActionResult`.
- **Tools**: Proxies calls to an external MCP server (e.g. `issue_refund`, `cancel_order`).
- **Failure/Edge cases**:
  - Mutating operations require an `idempotency_key` constructed from `session_id + turn_id + action_type`. It writes this key to `approvals.executed_actions` before executing. On retry, it skips execution and returns the previous result, preventing double-billing or duplicate actions.

## 3. `escalation_agent` (HITL & Handoff)
- **Purpose**: Pauses the system for human operator approval or fully hands off the conversation to a human agent.
- **Input/Output**: `EscalationRequest` → `EscalationResult`.
- **Surprising/Non-obvious behavior**:
  - Entirely stateless across turns. It calls `interrupt()` to freeze the LangGraph state in the Postgres checkpointer. The state remains frozen until an operator calls `POST /api/v1/.../approvals/{id}/approve`, which signals the ARQ worker to unpause the graph using `Command(resume=decision)`.
  - Also pushes a Redis notification to the operator channel on escalation.

## 4. `retrieval_agent` (Knowledge/FAQ)
- **Purpose**: Answers knowledge and policy questions strictly from the vector database. READ-ONLY.
- **Input/Output**: `RetrievalRequest` → `RetrievalResult`.
- **Surprising/Non-obvious behavior**:
  - Employs a **HyDE** (Hypothetical Document Embeddings) pattern via the `rewrite_query` node: it uses an LLM to generate a declarative statement, a hypothetical answer, and keywords *before* doing the vector search.
  - Returns `"I don't have enough information in the knowledge base to answer this question."` if chunks are insufficient. This signals the Orchestrator to escalate or ask for clarification.
  - **Note**: The code currently executes dense vector similarity search only. Docstrings mentioning BM25 and cross-encoder reranking do not reflect the actual implementation.

## Agent Config

Each workspace stores its LLM configuration in `workspace_agent_config`:
- `active_provider`: Which LLM provider to use (`openai`, `anthropic`, `ollama`, etc.)
- `global_model` / `global_temperature` / `global_system_prompt`: Applied to all agents unless `mode = "custom"`
- `mode = "custom"`: Enables per-agent model overrides via `custom_models` (JSONB)
- `custom_hitl_breakpoints`: List of action types that are always escalated regardless of the guardrail's risk assessment

*Last verified against: `support_system/root_agent/graph.py`, `support_system/subagents/[action|escalation|retrieval]/graph.py`, `backend/services/chat_service.py` — 2026-09-28.*
