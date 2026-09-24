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

async def get_workspace_summary(db: AsyncSession, workspace_id: UUID) -> dict:
    import asyncio
    from backend.db.models.approvals import ApprovalRequest
    from backend.db.models.chat import Conversation
    from sqlalchemy import desc, func
    
    # 1. Fetch top 3 urgent pending approvals (oldest first)
    approvals_stmt = (
        select(ApprovalRequest)
        .where(ApprovalRequest.workspace_id == workspace_id, ApprovalRequest.status == "pending")
        .order_by(ApprovalRequest.created_at.asc())
        .limit(3)
    )
    
    # 2. Fetch recent 5 conversations
    conv_stmt = (
        select(Conversation)
        .where(Conversation.workspace_id == workspace_id)
        .order_by(desc(Conversation.created_at))
        .limit(5)
    )
    
    # 3. Stats (just total pending approvals and total conversations for now)
    total_app_stmt = select(func.count(ApprovalRequest.id)).where(ApprovalRequest.workspace_id == workspace_id, ApprovalRequest.status == "pending")
    total_conv_stmt = select(func.count(Conversation.id)).where(Conversation.workspace_id == workspace_id)
    
    # Run them concurrently
    app_res, conv_res, total_app_res, total_conv_res = await asyncio.gather(
        db.execute(approvals_stmt),
        db.execute(conv_stmt),
        db.execute(total_app_stmt),
        db.execute(total_conv_stmt)
    )
    
    pending_approvals = app_res.scalars().all()
    recent_conversations = conv_res.scalars().all()
    total_pending = total_app_res.scalar_one_or_none() or 0
    total_convs = total_conv_res.scalar_one_or_none() or 0
    
    # Mapping to dicts
    approvals_out = [
        {
            "id": a.id,
            "session_id": a.session_id,
            "agent_id": a.agent_id,
            "action_type": a.action_type,
            "risk_level": a.risk_level,
            "status": a.status,
            "created_at": a.created_at,
            "expires_at": a.expires_at,
            "payload": a.payload,
            "reviewer_role": a.reviewer_role,
        } for a in pending_approvals
    ]
    
    conversations_out = [
        {
            "id": c.id,
            "workspace_id": c.workspace_id,
            "user_id": c.user_id,
            "metadata_": c.metadata_,
            "status": c.status,
            "created_at": c.created_at,
            "updated_at": c.updated_at
        } for c in recent_conversations
    ]
    
    return {
        "pending_approvals": approvals_out,
        "recent_conversations": conversations_out,
        "stats": {
            "total_pending_approvals": total_pending,
            "total_conversations": total_convs,
            "resolution_rate": "98.5%", # mock
            "avg_handling_time": "1m 45s" # mock
        },
        "system_health": "Healthy"
    }
