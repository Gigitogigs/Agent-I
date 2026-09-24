"""
backend/api/schemas/auth.py

Pydantic request/response models for the authentication flow.
These are the shapes the API exposes — they are decoupled from the SQLAlchemy ORM models.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return v

    @field_validator("full_name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Full name cannot be blank.")
        return v.strip()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    """Only used for JSON-body refresh; cookie-based refresh omits this."""
    refresh_token: str


class PasswordResetRequestBody(BaseModel):
    email: EmailStr


class PasswordResetConfirmBody(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return v


# ---------------------------------------------------------------------------
# Response bodies
# ---------------------------------------------------------------------------

class TokenResponse(BaseModel):
    """
    Returned by /refresh.
    """
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access token expires

class LoginUserOut(BaseModel):
    id: str
    name: str
    email: str
    avatarUrl: Optional[str] = None

class LoginResponse(BaseModel):
    user: LoginUserOut
    activeWorkspaceId: Optional[str] = None
    workspaceDeletionStatus: Optional[str] = None
    
    # We include these for mobile compatibility
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class MessageResponse(BaseModel):
    """Generic single-message response for logout, reset-request, etc."""
    message: str
