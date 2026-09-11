-- approvals/executed_actions.sql
-- Schema for idempotency tracking to prevent double-execution of mutating actions.

CREATE TABLE IF NOT EXISTS approvals.executed_actions (
    idempotency_key TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL,
    turn_id         TEXT NOT NULL,
    action_type     TEXT NOT NULL,
    payload         JSONB NOT NULL,
    status          TEXT NOT NULL DEFAULT 'completed'
                        CHECK (status IN ('pending', 'completed', 'failed')),
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- Note: When executing mutating actions, use a transaction:
-- 1. BEGIN
-- 2. INSERT INTO approvals.executed_actions (idempotency_key, ...) VALUES (...) ON CONFLICT DO NOTHING
-- 3. If inserted, proceed with external tool call
-- 4. UPDATE status based on tool call result
-- 5. COMMIT
