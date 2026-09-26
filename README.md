# Autonomi Support System (Agent-I)

The Autonomi Support System is a production-bound multi-agent customer support backend. It orchestrates language model agents (via LangGraph) to resolve customer inquiries, retrieve knowledge, and execute authorized actions on external systems, while enforcing safety guardrails and Human-in-the-Loop (HITL) approvals for high-risk operations.

### Quickstart (Bare-metal)
1. **Clone and Install**
   ```bash
   git clone <repository_url>
   cd Agent-I
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. **Setup Infrastructure**
   - Start PostgreSQL (with `pgvector` extension) and Redis.
3. **Configure Environment**
   - Create a `.env` file (see `SETUP.md` for all variables).
   ```bash
   DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/support_system
   REDIS_URL=redis://localhost:6379/0
   ENCRYPTION_KEY=<64_character_hex_string>
   ```
4. **Run DB Migrations**
   ```bash
   alembic upgrade head
   ```
5. **Start Services**
   - Terminal 1 (API Server): `uvicorn backend.main:app --host 0.0.0.0 --port 8000`
   - Terminal 2 (Background Worker): `python -m arq backend.worker.WorkerSettings`

### Prerequisites
- Python 3.12+
- PostgreSQL (with `pgvector` enabled)
- Redis
- Valid LLM provider API keys (e.g., OpenAI, Anthropic)

### Current Status
- **Backend**: FastAPI REST endpoints for chat, workspaces, and agents. (WebSockets are not yet implemented).
- **Agents**: Orchestrator, Action, Retrieval, and Escalation agents are implemented via LangGraph.
- **Safety**: Guardrails evaluate action risks. High-risk actions trigger HITL (Human-in-the-Loop) pauses via ARQ/LangGraph interrupts.
- **Frontend**: The Next.js admin frontend lives in a separate repository and communicates via HTTP.

> **Note:** A containerized setup (`docker-compose.yml`) is planned but not currently available. Please use the bare-metal setup instructions.

*Last verified against commit/code state: Checked backend/main.py, support_system/root_agent/graph.py, and backend/core/config.py.*
