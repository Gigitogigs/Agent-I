"""
backend/api/schemas/user.py

Pydantic models for user and membership responses.
Never exposes password_hash, reset tokens, or internal fields.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr


class MembershipOut(BaseModel):
    """A user's role within a single workspace, embedded in UserOut."""
    workspace_id: UUID
    workspace_name: str
    role: str

    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    """Safe public representation of a user. Returned by /me."""
    id: UUID
    email: EmailStr
    full_name: str
    avatar_url: Optional[str] = None
    created_at: datetime
    memberships: list[MembershipOut] = []

    model_config = {"from_attributes": True}


class UserUpdateRequest(BaseModel):
    """Body for PATCH /auth/me. All fields optional."""
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
