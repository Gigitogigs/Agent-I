CREATE TABLE IF NOT EXISTS approvals.approval_requests (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  TEXT NOT NULL,          -- scopes to one conversation
    agent_id    TEXT NOT NULL,          -- which agent generated this
    action_type TEXT NOT NULL,          -- 'refund', 'order_change', etc.
    payload     JSONB NOT NULL,         -- the full action parameters
    status      TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'approved', 'rejected', 'expired', 'cancelled')),
    reviewer_role TEXT,                 -- which role is authorised to act
    risk_level  TEXT NOT NULL DEFAULT 'medium'
                    CHECK (risk_level IN ('low', 'medium', 'high', 'critical')),
    expires_at  TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    resolved_by TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Enable Row-Level Security
ALTER TABLE approvals.approval_requests ENABLE ROW LEVEL SECURITY;

-- Policy: agents can only see their own session's requests
CREATE POLICY agent_isolation ON approvals.approval_requests
    USING (session_id = current_setting('app.current_session_id', true));