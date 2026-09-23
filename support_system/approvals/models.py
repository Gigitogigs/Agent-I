from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime
from uuid import UUID


# ---------------------------------------------------------------------------
# DB-layer model — mirrors the approvals.approval_requests table schema
# ---------------------------------------------------------------------------

class ApprovalRequest(BaseModel):
    """
    Represents a single row in approvals.approval_requests.

    State machine:
        pending → approved   (operator approved within SLA)
        pending → rejected   (operator rejected within SLA)
        pending → expired    (SLA elapsed; default policy: auto-escalate)
        pending → cancelled  (action superseded or session terminated)

    Cross-agent isolation is enforced at the Postgres RLS layer (rls_policies.sql),
    not here — do not rely on application code to enforce isolation.
    """
    id: Optional[UUID] = None                   # set by DB (gen_random_uuid)
    session_id: str                             # scopes row to one conversation
    agent_id: str                               # which subagent generated this
    action_type: str                            # e.g. 'issue_refund', 'cancel_order'
    payload: dict                               # full proposed action parameters
    status: Literal["pending", "approved", "rejected", "expired", "cancelled"] = "pending"
    reviewer_role: Optional[str] = None        # RBAC role authorised to act
    risk_level: Literal["low", "medium", "high", "critical"] = "medium"
    expires_at: Optional[datetime] = None      # SLA deadline
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None          # operator ID who decided
    created_at: Optional[datetime] = None      # set by DB default (now())
