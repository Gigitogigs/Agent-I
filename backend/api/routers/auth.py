"""
backend/api/routers/auth.py

Authentication routes:
  POST /auth/register          — create account
  POST /auth/login             — email + password → tokens
  POST /auth/refresh           — rotate refresh token
  POST /auth/logout            — invalidate refresh token
  GET  /auth/me                — current user profile
  PATCH /auth/me               — update display name / avatar
  POST /auth/reset-password/request  — send reset email (stubbed)
  POST /auth/reset-password/confirm  — apply new password
"""
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from backend.api.dependencies import get_db, get_current_user
from backend.api.schemas.auth import (
    LoginRequest,
    MessageResponse,
    PasswordResetConfirmBody,
    PasswordResetRequestBody,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from backend.api.schemas.user import MembershipOut, UserOut, UserUpdateRequest
from backend.core.config import settings
from backend.db.models.user import User
from backend.services import (
    authenticate_user,
    confirm_password_reset,
    create_session,
    logout,
    refresh_session,
    register_user,
    request_password_reset,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# ---------------------------------------------------------------------------
# Cookie helpers
# ---------------------------------------------------------------------------

REFRESH_COOKIE_NAME = "refresh_token"

def _set_refresh_cookie(response: Response, raw_refresh: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=raw_refresh,
        httponly=True,
        secure=True,          # HTTPS only in production; override with env var for dev
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/v1/auth",  # Scoped: cookie is only sent to the auth routes
    )

def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path="/api/v1/auth")


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new account",
)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    user = await register_user(db, email=body.email, full_name=body.full_name, password=body.password)
    return _user_to_out(user)


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and receive tokens",
)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    user = await authenticate_user(db, email=body.email, password=body.password)
    access_token, raw_refresh = await create_session(
        db,
        user,
        user_agent=request.headers.get("User-Agent"),
        ip_address=request.client.host if request.client else None,
    )
    _set_refresh_cookie(response, raw_refresh)
    return TokenResponse(
        access_token=access_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------

@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate refresh token and receive new access token",
)
async def refresh(
    response: Response,
    db: AsyncSession = Depends(get_db),
    # Accept the token from the HttpOnly cookie (primary) or JSON body (fallback for mobile)
    cookie_refresh: Optional[str] = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
    body: Optional[RefreshRequest] = None,
):
    raw_refresh = cookie_refresh or (body.refresh_token if body else None)
    if not raw_refresh:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not provided.",
        )

    access_token, new_raw_refresh = await refresh_session(db, raw_refresh)
    _set_refresh_cookie(response, new_raw_refresh)
    return TokenResponse(
        access_token=access_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Invalidate refresh token and clear session",
)
async def logout_route(
    response: Response,
    db: AsyncSession = Depends(get_db),
    cookie_refresh: Optional[str] = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
    _current_user: User = Depends(get_current_user),
):
    if cookie_refresh:
        await logout(db, cookie_refresh)
    _clear_refresh_cookie(response)
    return MessageResponse(message="Logged out successfully.")


# ---------------------------------------------------------------------------
# /me — read & update
# ---------------------------------------------------------------------------

@router.get(
    "/me",
    response_model=UserOut,
    summary="Get current user profile",
)
async def me(current_user: User = Depends(get_current_user)):
    return _user_to_out(current_user)


@router.patch(
    "/me",
    response_model=UserOut,
    summary="Update display name or avatar",
)
async def update_me(
    body: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from datetime import datetime, timezone
    if body.full_name is not None:
        current_user.full_name = body.full_name
    if body.avatar_url is not None:
        current_user.avatar_url = body.avatar_url
    current_user.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(current_user)
    return _user_to_out(current_user)


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------

@router.post(
    "/reset-password/request",
    response_model=MessageResponse,
    summary="Request a password reset link",
)
async def password_reset_request(
    body: PasswordResetRequestBody,
    db: AsyncSession = Depends(get_db),
):
    raw_token = await request_password_reset(db, email=body.email)

    # Always return 200 OK regardless of whether the email exists (prevents enumeration).
    # TODO: In production, send an email here. raw_token is returned in the response
    # temporarily for development convenience.
    response_message = "If that email exists, a password reset link has been sent."
    if raw_token:
        # Dev-only — remove before shipping to prod
        response_message += f" [DEV] Token: {raw_token}"
    return MessageResponse(message=response_message)


@router.post(
    "/reset-password/confirm",
    response_model=MessageResponse,
    summary="Apply a new password using the reset token",
)
async def password_reset_confirm(
    body: PasswordResetConfirmBody,
    db: AsyncSession = Depends(get_db),
):
    await confirm_password_reset(db, raw_token=body.token, new_password=body.new_password)
    return MessageResponse(message="Password has been reset. You can now log in.")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _user_to_out(user: User) -> UserOut:
    """Map ORM User → UserOut Pydantic model."""
    memberships = []
    for m in getattr(user, "workspaces", []):
        memberships.append(
            MembershipOut(
                workspace_id=m.workspace_id,
                workspace_name=m.workspace.name if m.workspace else "",
                role=m.role,
            )
        )
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        avatar_url=user.avatar_url,
        created_at=user.created_at,
        memberships=memberships,
    )
