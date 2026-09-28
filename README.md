# Agent-I — Multi-Agent Customer Support System

A production-bound multi-agent customer support backend built with **LangGraph**, **FastAPI**, **PostgreSQL/pgvector**, and **Redis**.

## Documentation

| Document | Description |
|---|---|
| [SETUP.md](SETUP.md) | Prerequisites, environment variables, and how to run the system (bare-metal & Docker) |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design, agent graph flow, WebSocket streaming, and HITL sequence diagram |
| [AGENTS.md](AGENTS.md) | Per-agent reference: purpose, I/O contracts, and surprising edge-case behaviors |
| [API_REFERENCE.md](API_REFERENCE.md) | All REST and WebSocket endpoints grouped by router |
| [OPERATIONS.md](OPERATIONS.md) | Runbooks for stuck approvals, failed ingestion, HITL management, and DB operations |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Code layout conventions, migration workflow, and safe-change guidance |
| [FRONTEND.md](FRONTEND.md) | Interaction contract for the external Next.js admin frontend |

## System at a Glance

```
Customer / Widget
      │ HTTP POST or WebSocket
      ▼
FastAPI (backend/)
      │ invokes LangGraph
      ▼
root_agent (orchestrator) ──┬── retrieval_agent  (pgvector RAG)
                            ├── action_agent     (MCP / external tools)
                            └── escalation_agent (HITL, pauses graph via interrupt())
                                        │
                              Redis notification
                                        │
                              Human operator approves via API
                                        │
                              ARQ worker resumes graph
```

## Quick Start

Choose your deployment method:

**Docker (recommended)**
```bash
cp .env.example .env   # fill in ENCRYPTION_KEY and any LLM API keys
docker compose up -d
docker compose exec api alembic upgrade head
```

**Bare-metal**
```bash
uv pip install -r requirements.txt
alembic upgrade head
uvicorn backend.main:app --reload                     # API server
python -m arq backend.worker.WorkerSettings           # Background worker
```

See [SETUP.md](SETUP.md) for the full environment variable reference and prerequisites.

## Key Technical Notes

- **Chat transport**: Both HTTP (`POST .../chat`) and WebSocket (`WS .../ws`) are supported. WebSocket streams tokens in real-time.
- **Idempotency**: The chat and approval endpoints accept an optional `Idempotency-Key` header. Duplicate requests within 24 hours return the cached response and never re-invoke the agent.
- **HITL**: High-risk actions trigger `escalation_agent`, which calls `interrupt()` to freeze the LangGraph state in Postgres. An operator approves via the API; the ARQ worker resumes the graph.
- **Multi-tenancy**: All resources are scoped by `workspace_id`. The `WorkspaceContextMiddleware` injects this from the JWT on every request.
- **Interactive API docs**: Available at `http://localhost:8000/api/v1/docs` when the server is running.
