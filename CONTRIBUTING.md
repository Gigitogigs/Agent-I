# Contributing

## Code Organization
- **`backend/`**: Contains the FastAPI server, database models, background ARQ worker, and API routers.
  - Endpoints belong in `backend/api/routers`.
  - Database models belong in `backend/db/models` and must be imported in `backend/db/base.py` for Alembic to track them.
- **`support_system/`**: Contains the LangGraph agents and orchestration logic.
  - Agents belong in `support_system/subagents/<agent_name>/`.
  - Each agent should expose a `graph.py` containing the `StateGraph` definition and a `@tool` wrapped function for the Orchestrator to call.
  - Schema definitions for agents belong in `schema.py` inside their respective directories.

## Development Workflows
- **Testing**: Tests are located in `backend/tests/` and `support_system/tests/`. Run them via `pytest`.
- **Type Checking**: The project uses Pyright (`pyproject.toml` config). 
- **DB Migrations**: When adding a new model or field, generate a new Alembic migration:
  ```bash
  alembic revision --autogenerate -m "Add new feature"
  alembic upgrade head
  ```

## Safe Changes
- Due to the nature of LangGraph checkpointer serialization, if you change an agent's `AgentState` TypedDict, you *may* break in-flight paused graphs (HITL). Exercise caution when deploying state schema changes.
- New action tools must be added to the MCP server and mapped in `action_agent/graph.py`. Mutating tools must ensure they pass the `idempotency_key`.

*Last verified against commit/code state: Checked pyproject.toml, backend structure, and support_system conventions.*
