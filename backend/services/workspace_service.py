from datetime import datetime, timezone
from typing import List
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.core.security import verify_password
from backend.db.models.workspace import Workspace
from backend.db.models.workspace_member import WorkspaceMember
from backend.db.models.user import User

async def get_user_workspaces(db: AsyncSession, user: User) -> List[dict]:
    """Return all active workspaces a user is a member of."""
    stmt = (
        select(WorkspaceMember)
        .where(WorkspaceMember.user_id == user.id)
        .where(WorkspaceMember.status == "active")
        .options(selectinload(WorkspaceMember.workspace))
    )
    result = await db.execute(stmt)
    memberships = result.scalars().all()
    
    out = []
    for m in memberships:
        if m.workspace:
            out.append({
                "id": m.workspace.id,
                "name": m.workspace.name,
                "role": m.role,
                "deletion_scheduled_at": m.workspace.deletion_scheduled_at
            })
    return out

async def create_workspace(db: AsyncSession, name: str, user: User) -> dict:
    """Create a new workspace and add the creator as the owner."""
    workspace = Workspace(name=name)
    db.add(workspace)
    await db.flush() # get workspace ID
    
    member = WorkspaceMember(
        workspace_id=workspace.id,
        user_id=user.id,
        role="owner",
        status="active"
    )
    db.add(member)
    await db.commit()
    await db.refresh(workspace)
    
    return {
        "id": workspace.id,
        "name": workspace.name,
        "role": "owner",
        "deletion_scheduled_at": workspace.deletion_scheduled_at
    }

async def rename_workspace(db: AsyncSession, workspace_id: UUID, new_name: str) -> dict:
    """Rename an existing workspace and return the updated details."""
    workspace = await db.scalar(select(Workspace).where(Workspace.id == workspace_id))
    if not workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")
        
    workspace.name = new_name
    await db.commit()
    await db.refresh(workspace)
    
    return {
        "id": workspace.id,
        "name": workspace.name,
        "role": "owner",
        "deletion_scheduled_at": workspace.deletion_scheduled_at
    }

async def ensure_default_workspace(db: AsyncSession, user: User) -> WorkspaceMember:
    """Create a default workspace for a user if they have none, and return the membership."""
    workspace = Workspace(name=f"{user.full_name}'s Workspace")
    db.add(workspace)
    await db.flush()
    
    member = WorkspaceMember(
        workspace_id=workspace.id,
        user_id=user.id,
        role="owner",
        status="active"
    )
    db.add(member)
    await db.commit()
    
    # Reload with workspace eager loaded to match existing expectations
    stmt = (
        select(WorkspaceMember)
        .where(WorkspaceMember.id == member.id)
        .options(selectinload(WorkspaceMember.workspace))
    )
    member_reloaded = await db.scalar(stmt)
    return member_reloaded

async def schedule_workspace_deletion(db: AsyncSession, workspace_id: UUID, user: User, password: str) -> None:
    """Soft delete a workspace. Owner only (enforced at router level)."""
    if not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password."
        )
    
    workspace = await db.scalar(select(Workspace).where(Workspace.id == workspace_id))
    if not workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")
        
    workspace.deletion_scheduled_at = datetime.now(timezone.utc)
    await db.commit()
    
    # TODO: Enqueue confirmation email
    print(f"[BACKGROUND] Sending workspace deletion confirmation email to {user.email} for workspace {workspace.name}")

async def cancel_workspace_deletion(db: AsyncSession, workspace_id: UUID) -> None:
    """Cancel a pending workspace deletion."""
    workspace = await db.scalar(select(Workspace).where(Workspace.id == workspace_id))
    if not workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")
        
    workspace.deletion_scheduled_at = None
    await db.commit()
