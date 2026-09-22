from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field

# ---------------------------------------------------------------------------
# Workspace Members
# ---------------------------------------------------------------------------

class MemberOut(BaseModel):
    """
    Representation of a user within a workspace team list.
    If the user has not accepted the invite, id and name are None, and status is "pending".
    """
    id: Optional[UUID] = None
    name: Optional[str] = None
    email: EmailStr
    role: str
    status: str
    last_active_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

class MemberInvite(BaseModel):
    email: EmailStr
    role: str = Field(..., pattern="^(admin|operator|read-only)$")

class MemberUpdate(BaseModel):
    role: str = Field(..., pattern="^(admin|operator|read-only)$")
