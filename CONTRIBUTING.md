# Contributing

> Last verified against: `pyproject.toml`, `backend/`, `support_system/` — 2026-09-28.

## Code Organization

```
Agent-I/
├── backend/
│   ├── api/
│   │   ├── routers/        # One file per resource group
│   │   ├── schemas/        # Pydantic request/response models
│   │   ├── dependencies.py # FastAPI Depends() helpers (auth, DB, roles)
│   │   └── ws_manager.py   # WebSocket ConnectionManager (singleton)
│   ├── core/
│   │   ├── config.py       # Settings loaded from .env
│   │   ├── security.py     # JWT encode/decode
│   │   └── arq.py          # ARQ Redis pool helper
│   ├── db/
│   │   ├── base.py         # SQLAlchemy declarative base
│   │   ├── models/         # One file per DB table group
│   │   └── session.py      # Async engine + checkpointer/store pools
│   ├── middleware/         # WorkspaceContextMiddleware
│   ├── services/           # Business logic (no direct router imports)
│   ├── main.py             # FastAPI app, lifespan, middleware, router registration
│   ├── worker.py           # ARQ WorkerSettings + task functions
│   └── scheduler.py        # APScheduler (hourly cleanup)
└── support_system/
    ├── root_agent/         # Orchestrator LangGraph
    ├── subagents/
    │   ├── action_agent/
    │   ├── escalation_agent/
    │   └── retrieval_agent/
    └── harness/
        └── model_factory.py  # Builds LangChain chat models from agent_config dict
```

## Development Workflows

### Running Tests
```bash
.venv/Scripts/pytest.exe backend/tests -v
```

Tests use a separate `support_system_test` PostgreSQL database that is created and torn down automatically. Ensure Postgres is running and `DB_URL` in your environment points to a valid Postgres instance.

### Type Checking
```bash
pyright
```
Config is in `pyproject.toml` (`[tool.pyright]`).

### Database Migrations
When adding or modifying a model:
```bash
alembic revision --autogenerate -m "Describe the change"
alembic upgrade head
```

Ensure the new model is imported in `backend/db/base.py` so Alembic can detect it.

## Adding a New API Endpoint

1. Create or extend a file in `backend/api/routers/`.
2. Create Pydantic schemas in `backend/api/schemas/`.
3. Implement business logic in `backend/services/` (routers should stay thin).
4. Register the router in `backend/main.py` with `app.include_router(...)`.

## Adding a New Agent Tool

1. Implement the tool as a `@tool`-decorated function in the relevant subagent's `graph.py`.
2. Register it on the MCP server (for `action_agent` tools).
3. Add the tool name to the orchestrator tool list in `support_system/root_agent/graph.py`.
4. **For mutating tools**: implement idempotency by writing an `idempotency_key` (= `session_id + turn_id + action_type`) to `approvals.executed_actions` before execution.

## Safe Change Checklist

- **LangGraph state schema changes**: Changing an `AgentState` TypedDict may break in-flight graphs frozen in the Postgres checkpointer. Drain all pending HITL approvals before deploying.
- **WebSocket connection limit**: `ConnectionManager` supports one connection per `conversation_id`. Do not make it concurrent without implementing a proper pub/sub layer first.
- **Idempotency**: Any new endpoint that is not idempotent by nature should consider supporting the `Idempotency-Key` header pattern already used in `chat.py` and `approvals.py`.
