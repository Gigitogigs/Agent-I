# Operations & Runbook

This document covers operational procedures based on existing code paths. 

## 1. DB Cleanup & Background Jobs
- **Workspace/User Hard Deletion**: The FastAPI server runs an APScheduler (`backend/scheduler.py`) that executes `run_deletion_cleanup` hourly. This permanently deletes workspaces, accounts, conversations, and pgvector embeddings that have passed a 48-hour grace period.
- **Troubleshooting**: If a workspace is not deleting, check the FastAPI stdout logs for `[ERROR] Failed to delete workspace`. The SQL queries use CASCADE deletes, but missing relationships might cause integrity errors.

## 2. Managing HITL (Human-in-the-Loop) Interventions
- **Symptom**: Customer conversation is stuck pending approval.
- **Action**: Check the `approval_requests` table in Postgres for the `conversation_id`. 
  ```sql
  SELECT id, status, action_type, expires_at FROM approval_requests WHERE conversation_id = '<uuid>';
  ```
- **Resolution**: A human must use the Frontend UI (or call `POST /api/v1/approvals/<id>/approve`) to unblock the agent. If the approval API fails, you can manually enqueue the ARQ task by publishing to Redis or updating the table and unpausing the graph via LangGraph SDK.

## 3. Clearing Stuck ARQ Queues
- ARQ worker manages document chunking and LangGraph resumptions.
- To clear stuck jobs, you may need to flush the Redis database used by ARQ (be careful as this drops all pending tasks):
  ```bash
  redis-cli -u redis://localhost:6379/0 FLUSHDB
  ```

## 4. Database Migrations
- Standard Alembic workflow applies:
  ```bash
  alembic upgrade head
  ```
- **Warning**: Ensure the PostgreSQL `vector` extension is active before running migrations.

## Not Yet Handled (Gaps)
- **Deploying/Releases**: No CI/CD pipelines or Dockerfiles exist in the repo yet.
- **Backups**: There is currently no backup mechanism implemented in the code.
- **Credential Rotation**: No automated credential rotation exists; you must manually update `.env` and restart the Uvicorn/ARQ processes.

*Last verified against commit/code state: Checked backend/scheduler.py, backend/worker.py, backend/api/routers/approvals.py.*
