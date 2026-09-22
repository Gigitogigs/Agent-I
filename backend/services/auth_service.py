"""
backend/services/auth_service.py

Business logic for the authentication flow. All DB access is async.

Responsibilities:
  - register_user      : create user, hash password, return UserOut
  - authenticate_user  : verify credentials, return User ORM object
  - create_session     : mint tokens, persist refresh hash to user_sessions
  - refresh_session    : validate refresh token, rotate, return new tokens
  - logout             : delete user_sessions row for the token
  - request_password_reset : generate & store reset token, (stub) send email
  - confirm_password_reset : validate token, update password hash, clear token
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.core.config import settings
from backend.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    hash_token,
    decode_token,
    generate_reset_token,
)
from backend.db.models.user import User, UserSession
from backend.db.models.workspace_member import WorkspaceMember
from backend.db.models.workspace import Workspace


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_token_pair(user_id: str) -> tuple[str, str]:
    """Return (access_token, refresh_token) for the given user ID."""
    access = create_access_token(subject=user_id)
    refresh = create_refresh_token(subject=user_id)
    return access, refresh


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

async def register_user(
    db: AsyncSession,
    email: str,
    full_name: str,
    password: str,
) -> User:
    """
    Create a new user account.

    Raises 409 if the email is already registered.
    """
    # Check for duplicate email
    existing = await db.scalar(select(User).where(User.email == email.lower()))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(
        email=email.lower(),
        full_name=full_name,
        password_hash=hash_password(password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Login / Authenticate
# ---------------------------------------------------------------------------

async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    """
    Verify email + password.

    Always raises 401 on failure (no distinction between wrong email / wrong
    password — prevents user enumeration attacks).
    """
    user: Optional[User] = await db.scalar(
        select(User).where(User.email == email.lower())
    )
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.deletion_scheduled_at is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is scheduled for deletion.",
        )
    return user


async def create_session(
    db: AsyncSession,
    user: User,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> tuple[str, str]:
    """
    Mint a token pair, persist the refresh hash to user_sessions.

    Returns (access_token, raw_refresh_token).
    """
    access_token, raw_refresh = _build_token_pair(str(user.id))

    session = UserSession(
        user_id=user.id,
        refresh_token_hash=hash_token(raw_refresh),
        user_agent=user_agent,
        ip_address=ip_address,
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(session)
    await db.commit()
    return access_token, raw_refresh


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------

async def refresh_session(db: AsyncSession, raw_refresh_token: str) -> tuple[str, str]:
    """
    Validate refresh token, delete old session row, mint new pair.

    Implements refresh token rotation — each refresh token can only be used once.
    Raises 401 if the token is invalid, expired, or not in user_sessions.
    """
    try:
        payload = decode_token(raw_refresh_token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token type mismatch.",
        )

    token_hash = hash_token(raw_refresh_token)
    session: Optional[UserSession] = await db.scalar(
        select(UserSession)
        .where(UserSession.refresh_token_hash == token_hash)
        .where(UserSession.expires_at > datetime.now(timezone.utc))
    )
    if not session:
        # Token was already used or never existed — potential replay attack.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is invalid or has already been used.",
        )

    user_id = payload["sub"]

    # Delete the old session (token rotation)
    await db.delete(session)

    # Mint and persist the new session
    access_token, new_raw_refresh = _build_token_pair(user_id)
    new_session = UserSession(
        user_id=UUID(user_id),
        refresh_token_hash=hash_token(new_raw_refresh),
        user_agent=session.user_agent,
        ip_address=session.ip_address,
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(new_session)
    await db.commit()
    return access_token, new_raw_refresh


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

async def logout(db: AsyncSession, raw_refresh_token: str) -> None:
    """
    Invalidate the session by deleting the refresh token hash from user_sessions.
    Silently succeeds if the token doesn't exist (idempotent).
    """
    token_hash = hash_token(raw_refresh_token)
    await db.execute(
        delete(UserSession).where(UserSession.refresh_token_hash == token_hash)
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------

async def request_password_reset(db: AsyncSession, email: str) -> Optional[str]:
    """
    Generate a reset token, persist its hash, and return the raw token.

    Returns None if no user with that email exists (caller should NOT reveal
    this to the client — always respond 200 OK to prevent enumeration).
    """
    user: Optional[User] = await db.scalar(
        select(User).where(User.email == email.lower())
    )
    if not user:
        return None

    raw_token = generate_reset_token()
    import hashlib
    user.reset_password_token = hashlib.sha256(raw_token.encode()).hexdigest()
    user.reset_password_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    await db.commit()

    # TODO: Send email via configured provider (SendGrid, Resend, etc.)
    # For now, return the raw token so it can be used in dev without email.
    return raw_token


async def confirm_password_reset(
    db: AsyncSession, raw_token: str, new_password: str
) -> None:
    """
    Validate a reset token and update the user's password.
    Clears the token after use to prevent replay.
    """
    import hashlib
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    user: Optional[User] = await db.scalar(
        select(User)
        .where(User.reset_password_token == token_hash)
        .where(User.reset_password_expires_at > datetime.now(timezone.utc))
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token is invalid or has expired.",
        )

    user.password_hash = hash_password(new_password)
    user.reset_password_token = None
    user.reset_password_expires_at = None
    user.updated_at = datetime.now(timezone.utc)
    await db.commit()


# ---------------------------------------------------------------------------
# Load current user (used by dependencies)
# ---------------------------------------------------------------------------

async def get_user_by_id(db: AsyncSession, user_id: str) -> User:
    """
    Load a user with their workspace memberships eagerly joined.
    Raises 401 if not found or scheduled for deletion.
    """
    user: Optional[User] = await db.scalar(
        select(User)
        .where(User.id == UUID(user_id))
        .where(User.deletion_scheduled_at.is_(None))
        .options(
            selectinload(User.workspaces).selectinload(WorkspaceMember.workspace)
        )
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )
    return user
