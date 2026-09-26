# Setup Guide

This guide covers the bare-metal local development setup for the Autonomi Support System. 

## Prerequisites
- **Python**: 3.12 or higher.
- **PostgreSQL**: Must have the `pgvector` extension installed and enabled.
- **Redis**: For the ARQ background worker and queue.

## 1. Environment Variables
Configuration is handled in `backend/core/config.py`. Create a `.env` file in the repository root.

| Variable | Purpose | Required | Example / Default | Code Reference |
| :--- | :--- | :--- | :--- | :--- |
| `PROJECT_NAME` | Name of the API project | Optional | `Autonomi Support System` | `backend/core/config.py` |
| `API_V1_STR` | API prefix | Optional | `/api/v1` | `backend/core/config.py` |
| `DATABASE_URL` | Async connection string for Postgres | **Yes** | `postgresql+asyncpg://user:pass@localhost:5432/db` | `backend/core/config.py` |
| `POSTGRES_CHECKPOINTER_SCHEMA` | Schema for LangGraph checkpoints | Optional | `checkpoints` | `backend/core/config.py` |
| `REDIS_URL` | Connection string for Redis | **Yes** | `redis://localhost:6379/0` | `backend/core/config.py`, `backend/worker.py` |
| `JWT_SECRET` | Secret used to sign JWTs | **Yes** | `supersecretkey_change_me_in_production` | `backend/core/config.py` |
| `JWT_ALGORITHM` | JWT signing algorithm | Optional | `HS256` | `backend/core/config.py` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token expiry time | Optional | `15` | `backend/core/config.py` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token expiry time | Optional | `7` | `backend/core/config.py` |
| `ENCRYPTION_KEY` | AES-256 key for encrypting provider API keys at rest | **Yes** | 64-char hex string | `backend/core/config.py` |
| `FRONTEND_URL` | URL of the separate frontend app for password links & CORS | **Yes** | `http://localhost:3000` | `backend/core/config.py` |

> **TODO: Verify** - Are there any API keys required for LLM access (e.g. `OPENAI_API_KEY`) that are read by Langchain but not explicitly in `config.py`? 

## 2. Local Bare-Metal Setup
Currently, the system is designed to run bare-metal locally. A Docker compose setup is pending.

### Initialize the Database
1. Connect to PostgreSQL and create the database:
   ```sql
   CREATE DATABASE support_system;
   \c support_system
   CREATE EXTENSION IF NOT EXISTS vector;
   ```
2. Run Alembic migrations to build the schema:
   ```bash
   alembic upgrade head
   ```

### Run the System
The system requires two processes to run concurrently.

**1. FastAPI Server**
Runs the core REST API and the APScheduler (for hourly cleanup jobs).
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

**2. ARQ Background Worker**
Processes heavy document tasks and executes LangGraph state resumes (e.g. after a HITL approval).
```bash
python -m arq backend.worker.WorkerSettings
```

## 3. Running Tests
*(This assumes a test suite exists in `backend/tests` and `support_system/tests` based on standard repo structure.)*
```bash
pytest backend/tests
pytest support_system/tests
```
> **TODO: Verify** - Does the test suite require a separate test database or override `DATABASE_URL` automatically? 

## 4. Common Failure Modes
- **ARQ Worker Startup Error**: "Error: Redis connection failed" -> Ensure Redis is running and `REDIS_URL` matches your local instance.
- **Migration Errors**: If Alembic complains about missing `vector` type, ensure `CREATE EXTENSION vector;` was run on the Postgres database.
- **Authentication Failures**: Ensure `FRONTEND_URL` is exactly matching the origin (no trailing slash) for CORS to allow the frontend request.

*Last verified against commit/code state: Checked backend/core/config.py, backend/worker.py, backend/main.py.*
