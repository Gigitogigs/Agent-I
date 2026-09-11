CREATE SCHEMA IF NOT EXISTS approvals;

CREATE TABLE IF NOT EXISTS approvals.executed_actions (
    idempotency_key TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL,
    turn_id         TEXT NOT NULL,
    action_type     TEXT NOT NULL,
    payload         JSONB NOT NULL,
    status          TEXT NOT NULL DEFAULT 'completed',
    executed_at     TIMESTAMPTZ DEFAULT now()
);

-- Index for quick lookups by session
CREATE INDEX idx_executed_actions_session ON approvals.executed_actions (session_id);
