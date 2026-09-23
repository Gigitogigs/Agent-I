"""
backend/api/dependencies.py

Reusable FastAPI dependencies:
  - get_db                  : yields an async DB session per request
  - get_current_user        : decodes Bearer token, loads user (raises 401)
  - get_current_membership  : loads workspace membership for request context (raises 403)
  - require_role            : factory returning a dependency that enforces role membership
"""
from collections.abc import AsyncGenerator
from typing import Optional
from uuid import UUID

from fastapi import Cookie, Depends, Header, HTTPException, Path, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.security import decode_token
from backend.db.models.user import User
from backend.db.models.workspace_member import WorkspaceMember
from backend.db.session import AsyncSessionLocal
from backend.services.auth_service import get_user_by_id

# ---------------------------------------------------------------------------
# DB session
# ---------------------------------------------------------------------------

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a scoped async DB session. Automatically closed on request end."""
    async with AsyncSessionLocal() as session:
        yield session


# ---------------------------------------------------------------------------
# Token extraction
# ---------------------------------------------------------------------------

_bearer_scheme = HTTPBearer(auto_error=False)


def _extract_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> str:
    """
    Extract the raw Bearer token from the Authorization header.
    Raises 401 if the header is missing or malformed.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


# ---------------------------------------------------------------------------
# Current user
# ---------------------------------------------------------------------------

async def get_current_user(
    token: str = Depends(_extract_token),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Decode the access token and return the corresponding User.

    Raises:
        401: Token is invalid, expired, wrong type, or user not found.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
    except JWTError:
        raise credentials_exception

    if payload.get("type") != "access":
        raise credentials_exception

    user_id: Optional[str] = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    return await get_user_by_id(db, user_id)


# ---------------------------------------------------------------------------
# Workspace membership
# ---------------------------------------------------------------------------

async def get_current_membership(
    workspace_id: UUID = Path(...),
    current_user: User = Depends(get_current_user),
) -> WorkspaceMember:
    """
    Resolve the current user's WorkspaceMember record for the workspace
    identified in the URL path parameter `workspace_id`.

    Raises:
        403: User is not a member of this workspace.
    """
    for membership in current_user.workspaces:
        if membership.workspace_id == workspace_id:
            return membership

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Workspace not found.",
    )


# ---------------------------------------------------------------------------
# Role-based access control (RBAC)
# ---------------------------------------------------------------------------

# Role hierarchy from least to most privileged.
_ROLE_HIERARCHY = ["read-only", "operator", "admin", "owner"]


def require_role(*allowed_roles: str):
    """
    Dependency factory that enforces role-based access.

    Usage:
        @router.delete(..., dependencies=[Depends(require_role("admin", "owner"))])

    Raises:
        403: User's role is not in `allowed_roles`.
    """
    def _check(member: WorkspaceMember = Depends(get_current_membership)) -> WorkspaceMember:
        if member.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires one of the following roles: {', '.join(allowed_roles)}.",
            )
        return member

    return _check


def require_min_role(min_role: str):
    """
    Dependency factory that enforces a minimum role level.

    Usage:
        @router.get(..., dependencies=[Depends(require_min_role("operator"))])

    Raises:
        403: User's role is below `min_role` in the hierarchy.
    """
    def _check(member: WorkspaceMember = Depends(get_current_membership)) -> WorkspaceMember:
        try:
            user_level = _ROLE_HIERARCHY.index(member.role)
            required_level = _ROLE_HIERARCHY.index(min_role)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Unknown role.",
            )
        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires at least the '{min_role}' role.",
            )
        return member

    return _check
