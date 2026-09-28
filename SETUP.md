# Setup Guide

> This covers both **bare-metal** and **Docker** deployments. Last verified 2026-09-28.

## Prerequisites

### Bare-metal
| Dependency | Version | Notes |
|---|---|---|
| Python | 3.12+ | The `.python-version` file pins this |
| PostgreSQL | 14+ | Must have the `pgvector` extension available |
| Redis | 7+ | Used for ARQ task queue and idempotency cache |
| `uv` | latest | Fast package installer (`pip install uv`) |

### Docker
- Docker Engine 24+ and Docker Compose v2

---

## Environment Variables

Create a `.env` file at the repo root. All variables below are read by `backend/core/config.py`.

| Variable | Required | Example | Notes |
|---|---|---|---|
| `DB_URL` | ✅ | `postgresql+asyncpg://postgres:pass@localhost:5432/support_system` | Must use `+asyncpg` driver |
| `REDIS_URL` | ✅ | `redis://localhost:6379/0` | Used by ARQ and idempotency cache |
| `ENCRYPTION_KEY` | ✅ | 32-byte base64 string | Used to encrypt provider API keys stored in DB |
| `EMBEDDING_MODEL` | ✅ | `qwen3-embedding:0.6b` | Ollama model name used for pgvector embeddings |
| `POSTGRES_CHECKPOINTER_SCHEMA` | ✅ | `checkpoints` | Schema for LangGraph state persistence |
| `SLACK_WEBHOOK_URL` | ❌ | `https://hooks.slack.com/...` | Optional — Slack notifications for HITL escalations |

> **LLM API Keys** are stored per-workspace in the database (`workspace_provider_keys` table), encrypted with `ENCRYPTION_KEY`. They are **not** read from environment variables at runtime; they are configured through the Providers API after setup.

---

## Bare-Metal Setup

### 1. Install Dependencies
```bash
uv pip install -r requirements.txt
```

### 2. Set Up PostgreSQL
```bash
# Create the database
psql -U postgres -c "CREATE DATABASE support_system;"

# Enable the pgvector extension
psql -U postgres -d support_system -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### 3. Configure Environment
```bash
cp .env.example .env
# Edit .env with your DATABASE_URL, REDIS_URL, and ENCRYPTION_KEY
```

### 4. Run Migrations
```bash
alembic upgrade head
```

> ⚠️ **Warning**: The `schema.sql` file in the repo root is a reference snapshot and may be out of sync with Alembic migrations. Always use `alembic upgrade head` as the source of truth.

### 5. Start Services

Open separate terminals for each process:

```bash
# Terminal 1 — API server
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — Background worker (document processing + HITL graph resumption)
python -m arq backend.worker.WorkerSettings
```

The APScheduler (hourly soft-delete cleanup) starts automatically inside the API process.

---

## Docker Setup

A `docker-compose.yml` and `Dockerfile` are included in the repo root.

```bash
# 1. Create your .env file
cp .env.example .env

# 2. Start all services (PostgreSQL, Redis, API server, ARQ worker)
docker compose up -d

# 3. Run migrations inside the API container
docker compose exec api alembic upgrade head
```

**Services defined in `docker-compose.yml`:**

| Service | Container | Port |
|---|---|---|
| PostgreSQL (pgvector) | `autonomi_db` | 5432 |
| Redis | `autonomi_redis` | 6379 |
| FastAPI server | `autonomi_api` | 8000 |
| ARQ worker | `autonomi_worker` | — |

> Both the `api` and `worker` services use the same `Dockerfile` (Python 3.12-slim with `uv`), started with different `command` values.

---

## Verifying the Installation

```bash
# Health check
curl http://localhost:8000/api/v1/health

# Interactive API docs
open http://localhost:8000/api/v1/docs
```

*Last verified against: `pyproject.toml`, `backend/core/config.py`, `docker-compose.yml`, `Dockerfile`, `alembic/`*
