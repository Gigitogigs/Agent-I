# Agent-I Pre-Production Review

## Executive Summary
**What's done well:**
- The multi-agent architecture is clean and stateless. Subagents operate independently and the orchestrator manages flow, minimizing failure domains.
- API structure and dependency injection for auth/RBAC is well-organized and modular.
- Background task offloading (ARQ) for heavy tasks (LangGraph execution, document indexing) prevents API blocking and ensures scalable performance.
- Secret masking on APIs is explicitly enforced (e.g., `IntegrationOut` drops the credentials `config` field).
- State checkpointing uses LangGraph's PostgresSaver, ensuring conversation state survives server restarts.
- **Auth Integrity:** Passwords use bcrypt, refresh tokens and reset tokens are securely hashed (SHA256) in the database before storage, preventing database leak exploitation.
- **Backend Adapter Pattern:** The MCP adapter architecture uses strict `Pydantic` schemas (`OrderStatusResult`, `RefundResult`), successfully shielding the LLM from backend-specific JSON shapes.

**Summary Table**

| Severity | Issue | Location |
|---|---|---|
| Blocker | Approvals API does not enforce `reviewer_role` | `backend/api/routers/approvals.py:34` |
| Blocker | Psycopg3 `autocommit` conflict crashes agent | `support_system/subagents/action_agent/graph.py:104` |
| Blocker | Missing `executed_actions` table crashes agent | `support_system/subagents/action_agent/graph.py:84` |
| Blocker | Failed agent actions are silently skipped on retry | `support_system/subagents/action_agent/graph.py:92` |
| Blocker | Postgres superuser bypasses RLS and context is unset | `backend/core/config.py:9` |
| Blocker | `rag.resolved_tickets` missing `workspace_id` | `schema.sql:169` |
| Blocker | Path Traversal in Document Uploads | `backend/api/routers/knowledge.py:86` |
| Blocker | Broken CORS Configuration | `backend/main.py:41` |
| Blocker | Alembic/SQL Migration Desync (Data Loss Risk) | `alembic/versions/283d6e9fdee8...` |

---

## Detailed Findings

*(...Previous Sections Omitted for Brevity...)*

---

## Documentation & Operational Support Review

A review of the project documentation from the perspective of a new engineer or a customer's IT team reveals that the system is currently un-deployable and un-supportable without direct help from the original authors.

### 1. Zero-to-Working System (The Clone Test)
- **The Reality:** The `README.md` is completely empty (0 bytes). There is no `.env.example`, no `docker-compose.yml`, and no setup script.
- **Missing Steps for a New Engineer:**
  1. How to install and configure PostgreSQL with the `pgvector` extension.
  2. How to start Redis for the ARQ queue.
  3. Which environment variables are required (`DATABASE_URL`, `REDIS_URL`, `ENCRYPTION_KEY`, etc.).
  4. How to run Alembic migrations (and a dire warning that the migrations are currently out of sync with `schema.sql`).
  5. The specific CLI commands to start the FastAPI server (`uvicorn`) and the ARQ worker (`arq`).
- **Verdict:** A new engineer or IT person could not get this system running.

### 2. Stale Claims (Code vs. Docs)
Several architectural documents contain aspirational claims that differ wildly from the actual codebase:
- **WebSockets:** `multi-agent-support-system-architecture.md` claims the primary channel is a real-time WebSocket. The code exclusively uses stateless HTTP POSTs (`backend/api/routers/chat.py`).
- **Data Isolation:** `Backend Architecture.md` claims Postgres RLS guarantees multi-tenant isolation. The code connects as a superuser, bypassing RLS entirely.
- **Hybrid Retrieval:** Docstrings in the RAG agent claim the system uses "hybrid retrieval, BM25 fallback, and cross-encoder reranking." The code only executes a basic dense vector similarity search.
- **Long-Term Memory:** The architecture claims to persist long-term customer facts. The codebase has absolutely no functions to write to the `store` memory.

### 3. Missing Runbooks
There are absolutely **no runbooks** in the repository. Operators are flying blind for critical incidents:
- **Stuck Approvals:** No runbook on how to clear them (especially since the database expiry cron doesn't exist).
- **Failed Ingestion:** No runbook on how to purge zombie documents stuck in the `"processing"` state forever.
- **Credential Rotation:** No runbook on how to rotate the `ENCRYPTION_KEY` without bricking every stored API key in the database.
- **Backup & Restore:** No documented strategy for `pg_dump`, point-in-time recovery, or vector index rebuilds.
- **Connecting New Backends:** No developer guide on how to implement the `AdapterProtocol` for custom clients.

### 4. API and Configuration Documentation
- **API Spec:** The API is documented manually in `API-Contract.md`. While generally accurate for the happy paths, it is a static markdown file rather than a standard OpenAPI/Swagger spec, meaning SDKs cannot be auto-generated. (FastAPI does auto-generate an OpenAPI spec at `/docs`, but this is not exported or documented in the repo).
- **Configuration:** Environment variables are entirely undocumented.

### 5. Operator / Customer Expectations
- **Agent Limits:** There is no user-facing documentation explaining what the agent *won't* do, or what strictly triggers a `HIGH` vs `CRITICAL` risk escalation. Operators have to read the raw Python code to understand the agent's boundaries.
- **System Limits:** There is no documentation warning customers about file upload size limits (because none are enforced, posing a DoS risk).

### 6. Prioritized Documentation Launch List
Before launch, the following documents must be written:
1. **`README.md` (Local Setup Guide):** Step-by-step instructions for DB setup, ENV vars, migrations, and starting the web/worker processes.
2. **`Runbooks.md` (Incident Management):** Step-by-step guides for DB restore, credential rotation, and clearing stuck queues.
3. **`Architecture.md` (Refresh):** Strip out all vaporware claims (WebSockets, Hybrid RAG, Long-Term Memory) to reflect the actual v1 codebase.
4. **`Integrations_Guide.md`:** A developer tutorial on adding a new backend adapter to the MCP layer.
