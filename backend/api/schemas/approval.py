from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Approvals
# ---------------------------------------------------------------------------

class ApprovalOut(BaseModel):
    """
    Representation of an approval request in the HITL dashboard.
    """
    id: UUID
    status: str
    riskLevel: str = Field(alias="risk_level")
    actionSummary: Optional[str] = Field(alias="action_type", default=None)
    agentName: Optional[str] = Field(alias="agent_id", default=None)
    conversationId: UUID = Field(alias="conversation_id")
    slaExpiresAt: Optional[datetime] = Field(alias="expires_at", default=None)
    createdAt: datetime = Field(alias="created_at")
    parameters: Dict[str, Any] = Field(alias="payload", default_factory=dict)
    conversationSummary: Optional[str] = None # Will populate this if we have a summary available
    resolvedAt: Optional[datetime] = Field(alias="resolved_at", default=None)
    resolvedBy: Optional[str] = None # We will map resolved_by_user_id to an email string manually
    rejectReason: Optional[str] = Field(alias="operator_note", default=None)

    model_config = {
        "from_attributes": True,
        "populate_by_name": True
    }

class ApprovalRejectBody(BaseModel):
    reason: str = Field(..., min_length=1, max_length=1000)
