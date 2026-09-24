from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Workspaces
# ---------------------------------------------------------------------------

class WorkspaceOut(BaseModel):
    """
    Representation of a workspace in the /workspaces list.
    Includes the user's role in that workspace.
    """
    id: UUID
    name: str
    role: str
    deletion_scheduled_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)

class PasswordConfirmBody(BaseModel):
    """Used for high-risk actions like deleting an account or workspace."""
    password: str

# ---------------------------------------------------------------------------
# Homepage Summary
# ---------------------------------------------------------------------------
from typing import Any, Dict, List

class HomepageSummaryOut(BaseModel):
    pending_approvals: List[Any]
    recent_conversations: List[Any]
    stats: Dict[str, Any]
    system_health: str
