# Operations & Runbook

> Last verified against: `backend/scheduler.py`, `backend/worker.py`, `backend/api/routers/approvals.py`, `backend/services/approval_service.py` — 2026-09-28.

---

## 1. Starting & Stopping Services

### Bare-metal
```bash
# Start API
uvicorn backend.main:app --host 0.0.0.0 --port 8000

# Start ARQ worker (separate terminal / process manager)
python -m arq backend.worker.WorkerSettings

# The APScheduler (hourly cleanup) starts automatically with the API process.
```

### Docker
```bash
docker compose up -d      # start all
docker compose down       # stop all (data persists in named volumes)
docker compose down -v    # stop and DELETE all data volumes
```

---

## 2. Scheduled Background Jobs

### Hourly Workspace Hard-Deletion (APScheduler)
- **What it does**: Permanently deletes workspaces, users, conversations, and pgvector embeddings that have passed their 48-hour grace period (soft-deleted via `scheduled_deletion_at`).
- **Where it runs**: Inside the FastAPI process (`backend/scheduler.py`).
- **Troubleshooting**: If a workspace is stuck, check FastAPI stdout for `[ERROR] Failed to delete workspace`. The SQL uses `CASCADE` deletes; integrity errors can occur if foreign keys are missing.

### Document Processing (ARQ Worker)
- **What it does**: Chunks and embeds uploaded documents into pgvector.
- **Stuck documents**: Documents stuck in `"processing"` status permanently (e.g. due to a crashed worker) must be manually reset:
  ```sql
  UPDATE rag.documents SET status = 'failed' WHERE status = 'processing' AND updated_at < NOW() - INTERVAL '1 hour';
  ```

---

## 3. Managing HITL (Human-in-the-Loop) Approvals

### Finding Stuck Conversations
```sql
SELECT id, conversation_id, action_type, status, created_at, expires_at
FROM approval_requests
WHERE status = 'pending'
ORDER BY created_at;
```

### Approving / Rejecting via API
```bash
# Approve
curl -X POST http://localhost:8000/api/v1/workspaces/{ws_id}/approvals/{app_id}/approve \
  -H "Authorization: Bearer <operator_token>"

# Reject
curl -X POST http://localhost:8000/api/v1/workspaces/{ws_id}/approvals/{app_id}/reject \
  -H "Authorization: Bearer <operator_token>" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Not authorised by policy"}'
```

> Both endpoints accept an `Idempotency-Key` header to prevent double-approval from UI retries.

### Manually Unblocking a Graph (Emergency)
If the approval API is unavailable, you can manually update the DB and enqueue the ARQ task:
```sql
UPDATE approval_requests SET status = 'approved', resolved_by_user_id = '<user_uuid>'
WHERE id = '<approval_uuid>';
```
Then republish the ARQ task:
```python
# In a Python shell with the venv activated
import asyncio
from arq import create_pool
from arq.connections import RedisSettings

async def enqueue():
    pool = await create_pool(RedisSettings.from_dsn("redis://localhost:6379/0"))
    await pool.enqueue_job("resume_agent_graph", "<thread_id>", "approved")

asyncio.run(enqueue())
```

---

## 4. Idempotency Key Cache

The Redis keys `idemp:chat:*`, `idemp:approve:*`, and `idemp:reject:*` have a 24-hour TTL.

To manually clear a stuck "in_progress" lock:
```bash
redis-cli DEL "idemp:chat:<your-idempotency-key>"
```

To flush all idempotency keys (be careful):
```bash
redis-cli --scan --pattern "idemp:*" | xargs redis-cli DEL
```

---

## 5. Database Migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Generate a new migration after model changes
alembic revision --autogenerate -m "Add new field"
alembic upgrade head
```

> ⚠️ **LangGraph state schema changes**: If you change an agent's `AgentState` TypedDict, in-flight paused graphs (frozen in the Postgres checkpointer) may fail to deserialize after the deployment. Drain all pending HITL approvals before deploying state-schema changes.

---

## 6. Credential Rotation

### Rotating `ENCRYPTION_KEY`
The `ENCRYPTION_KEY` is used to encrypt LLM provider API keys stored in `workspace_provider_keys`. There is currently **no automated re-encryption utility**. To rotate it:
1. Export all encrypted keys before the rotation.
2. Update `ENCRYPTION_KEY` in `.env`.
3. Re-enter all provider API keys through the UI or Providers API — they will be re-encrypted with the new key.

### Rotating Database / Redis Passwords
Update `.env` (and `docker-compose.yml` if using Docker), then restart all services.

---

## 7. Backup & Restore

No automated backup mechanism is implemented. Use standard PostgreSQL tooling:

```bash
# Backup
pg_dump -U postgres support_system > backup_$(date +%Y%m%d).sql

# Restore
psql -U postgres support_system < backup_20260928.sql
```

> The pgvector index will be recreated automatically on restore. For large embeddings tables, `REINDEX INDEX CONCURRENTLY` may be needed if performance degrades after restore.

---

## 8. Adding a New External Backend (AdapterProtocol)

The `action_agent` proxies calls to an external MCP server. To connect a new backend:
1. Implement the `AdapterProtocol` interface (see `support_system/harness/`).
2. Register your new tools on the MCP server and expose them as callable functions.
3. Add the tool names to the orchestrator's tool list in `support_system/root_agent/graph.py`.
4. Mutating tools **must** pass an `idempotency_key` (constructed as `session_id + turn_id + action_type`) and write it to `approvals.executed_actions` before execution.
