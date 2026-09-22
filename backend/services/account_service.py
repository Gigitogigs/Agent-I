from datetime import datetime, timezone
from typing import List

from fastapi import HTTPException, status
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.core.security import verify_password
from backend.db.models.user import User, UserSession
from backend.db.models.workspace_member import WorkspaceMember
from backend.db.models.workspace import Workspace

async def schedule_account_deletion(db: AsyncSession, user: User, password: str) -> None:
    """
    Soft delete an account and all workspaces they own.
    Invalidate all active sessions immediately.
    """
    if not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password."
        )
    
    now = datetime.now(timezone.utc)
    user.deletion_scheduled_at = now
    
    # Soft delete all workspaces owned by this user
    stmt = (
        select(WorkspaceMember)
        .where(WorkspaceMember.user_id == user.id)
        .where(WorkspaceMember.role == "owner")
        .options(selectinload(WorkspaceMember.workspace))
    )
    result = await db.execute(stmt)
    owned_memberships = result.scalars().all()
    
    for m in owned_memberships:
        if m.workspace and not m.workspace.deletion_scheduled_at:
            m.workspace.deletion_scheduled_at = now
            
    # Invalidate all active sessions
    await db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    
    await db.commit()
    
    # TODO: Enqueue confirmation email
    print(f"[BACKGROUND] Sending account deletion confirmation email to {user.email}")

async def cancel_account_deletion(db: AsyncSession, user: User) -> None:
    """Restore an account and all workspaces they own."""
    user.deletion_scheduled_at = None
    
    # Restore all workspaces owned by this user
    stmt = (
        select(WorkspaceMember)
        .where(WorkspaceMember.user_id == user.id)
        .where(WorkspaceMember.role == "owner")
        .options(selectinload(WorkspaceMember.workspace))
    )
    result = await db.execute(stmt)
    owned_memberships = result.scalars().all()
    
    for m in owned_memberships:
        if m.workspace:
            m.workspace.deletion_scheduled_at = None
            
    await db.commit()
