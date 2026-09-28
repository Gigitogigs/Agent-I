# Architecture

> Source of truth: `backend/`, `support_system/`, `backend/api/routers/`. Last verified 2026-09-28.

## 1. Process Model

Three long-running processes constitute the backend:

| Process | Start command | Role |
|---|---|---|
| **API server** | `uvicorn backend.main:app` | Serves HTTP and WebSocket connections |
| **ARQ worker** | `python -m arq backend.worker.WorkerSettings` | Runs background tasks (document processing, graph resumption) |
| **APScheduler** | Started automatically inside the API process via `lifespan` | Periodic cleanup (hourly hard-delete of soft-deleted workspaces) |

## 2. Chat Transport

The system exposes **two parallel chat interfaces** for the same conversation:

### 2a. HTTP (Stateless)
`POST /api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/chat`

- **Request**: `{ "message": "string" }` + optional `Idempotency-Key` header
- **Behavior**: Saves the user turn to Postgres, then calls `root_agent.invoke(...)` via `asyncio.to_thread` (blocking the LangGraph call off the async event loop), saves the agent turn, and returns the full response.
- **Idempotency**: If an `Idempotency-Key` header is present, the server acquires a Redis lock (`SET nx=True`). Duplicate in-flight requests get a `409 Conflict`. Once the response is produced, it is cached in Redis for 24 hours so subsequent retries return the cached result instantly.

### 2b. WebSocket (Streaming)
`WS /api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/ws`

- **Auth**: JWT passed in the `sec-websocket-protocol` header as `access_token.<token>`. Workspace membership is verified before the connection is accepted.
- **Protocol** (client → server):
  - `{ "type": "ping" }` → server replies `{ "type": "pong" }`
  - `{ "type": "message", "content": "..." }` → triggers the agent
- **Protocol** (server → client):
  - `{ "type": "agent_status", "status": "thinking" }` — sent immediately on message receipt
  - `{ "type": "token", "content": "..." }` — one frame per streamed LLM token (from `root_agent.astream_events`, filtered to the `synthesise` node)
  - `{ "type": "turn_complete", "turn_id": "...", "subagent_results": {...} }` — final frame once the full turn is saved to DB
  - `{ "type": "error", "detail": "..." }` — on any agent or parse error

The `ConnectionManager` in `backend/api/ws_manager.py` maintains a single `Dict[conversation_id → WebSocket]`, so only one active WebSocket per conversation is supported.

## 3. Agent Graph

```
root_agent (ReAct loop)
│
├─ guardrail_check  ← intercepts tool calls with HIGH/CRITICAL risk
│   └─ if risky: overrides tool call → escalation_agent
│
├─ retrieval_agent   (HyDE vector search against pgvector)
├─ action_agent      (MCP proxy: issue_refund, cancel_order, etc.)
│   └─ idempotency_key = session_id + turn_id + action_type
│       written to approvals.executed_actions before execution
└─ escalation_agent  (HITL)
    └─ calls interrupt() → graph state frozen in Postgres checkpointer
        └─ resumed by ARQ task `resume_agent_graph` after operator approval
```

## 4. HITL Approval Flow

```
root_agent
  │  guardrail detects HIGH risk
  ▼
escalation_agent
  │  1. Writes ApprovalRequest row (status=pending) to DB
  │  2. Publishes Redis notification to operator channel
  │  3. Calls interrupt() → graph freezes; HTTP/WS response still returns
  ▼
Operator calls POST /api/v1/workspaces/{id}/approvals/{id}/approve
  │  1. Sets ApprovalRequest.status = approved
  │  2. Enqueues ARQ task: resume_agent_graph(thread_id, decision)
  ▼
ARQ Worker
  │  Calls root_agent.ainvoke with Command(resume=decision)
  │  Graph unfreezes, action_agent executes the approved action
  ▼
WebSocket / next HTTP poll delivers final response
```

## 5. Data Stores

| Store | Purpose |
|---|---|
| **PostgreSQL** | Conversations, turns, workspaces, users, approval requests, document chunks (`rag` schema), LangGraph checkpoints (`checkpoints` schema), long-term memory (`memory_store` schema) |
| **pgvector** | Embedding index inside PostgreSQL (`rag.document_chunks.embedding`) |
| **Redis** | ARQ task queue, idempotency key cache (24h TTL), operator notifications |

## 6. Known Gaps (as of 2026-09-28)

- **Postgres RLS is not enforced**: The app connects as a superuser; multi-tenant isolation is enforced at the application layer (all queries filter by `workspace_id`).
- **Hybrid search not implemented**: RAG uses dense vector similarity only. BM25 and cross-encoder reranking mentioned in old docs are not present in the code.
- **One WebSocket per conversation**: `ConnectionManager` stores a single socket per `conversation_id`; a second connection silently replaces the first.

*Last verified against: `backend/main.py`, `backend/api/routers/ws_chat.py`, `backend/services/chat_service.py`, `support_system/root_agent/graph.py`, `support_system/subagents/*/graph.py`*
