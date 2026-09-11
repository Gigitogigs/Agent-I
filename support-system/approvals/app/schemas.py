# approvals/app/schemas.py
#
# Pydantic models for the HITL Approval REST API layer.
#
# These models are separate from approvals/models.py (which documents the DB
# state machine) — these schemas specifically define the HTTP request/response
# shapes consumed by the frontend operator UI.

from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime


class ApprovalDecisionRequest(BaseModel):
    """Payload sent by an operator when approving, rejecting, or cancelling."""
    status: Literal["approved", "rejected", "cancelled"]
    operator_note: Optional[str] = None
    resolved_by: str  # operator username / ID — required for audit trail


class ApprovalListItem(BaseModel):
    """Compact representation used in the pending-approvals dashboard list."""
    id: str
    session_id: str
    agent_id: str
    action_type: str
    risk_level: str
    status: str
    created_at: datetime
    expires_at: Optional[datetime] = None


class ApprovalDetailResponse(ApprovalListItem):
    """Full detail view — adds payload and reviewer_role for the decision UI."""
    payload: dict
    reviewer_role: Optional[str] = None


class DecisionResponse(BaseModel):
    """Response returned after an operator submits a decision."""
    status: str
    decision: str
    session_id: str
    warning: Optional[str] = None  # set when the DB committed but graph resume failed
