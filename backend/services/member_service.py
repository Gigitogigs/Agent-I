from typing import List
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.db.models.workspace_member import WorkspaceMember
from backend.db.models.user import User
from backend.db.models.workspace import Workspace

async def get_workspace_members(db: AsyncSession, workspace_id: UUID) -> List[dict]:
    """Get all members (active and pending) for a workspace."""
    stmt = (
        select(WorkspaceMember)
        .where(WorkspaceMember.workspace_id == workspace_id)
        .options(selectinload(WorkspaceMember.user))
    )
    result = await db.execute(stmt)
    memberships = result.scalars().all()
    
    out = []
    for m in memberships:
        # Pending invites might not have a full user object yet, or they might
        # be linked to a dummy user record depending on invite strategy. 
        # For simplicity, if status is pending and no user, we'll format accordingly.
        # But our schema requires user_id. Wait, if it's pending, user_id might 
        # point to a placeholder. Let's look up the email.
        
        email = m.user.email if m.user else "pending@example.com"
        name = m.user.full_name if m.user else None
        
        out.append({
            "id": m.user_id if m.status == "active" else None,
            "name": name if m.status == "active" else None,
            "email": email,
            "role": m.role,
            "status": m.status,
            "last_active_at": m.user.updated_at if m.user and m.status == "active" else None
        })
    return out

async def invite_member(db: AsyncSession, workspace_id: UUID, email: str, role: str, inviter: User) -> dict:
    """
    Invite a user by email.
    If the user already exists, add them as pending (or active depending on product rules).
    If they don't, create a placeholder user for the invite.
    """
    email = email.lower()
    
    # Check if user exists
    user = await db.scalar(select(User).where(User.email == email))
    if not user:
        # Create a placeholder user
        import secrets
        from backend.core.security import hash_password
        dummy_pass = secrets.token_hex(16)
        user = User(
            email=email,
            full_name="Pending User",
            password_hash=hash_password(dummy_pass)
        )
        db.add(user)
        await db.flush()
        
    # Check if already a member
    existing = await db.scalar(
        select(WorkspaceMember)
        .where(WorkspaceMember.workspace_id == workspace_id)
        .where(WorkspaceMember.user_id == user.id)
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member or has a pending invite."
        )
        
    member = WorkspaceMember(
        workspace_id=workspace_id,
        user_id=user.id,
        role=role,
        status="pending",
        invited_by_user_id=inviter.id
    )
    db.add(member)
    await db.commit()
    
    # TODO: Enqueue invite email
    print(f"[BACKGROUND] Sending invite email to {email} for workspace {workspace_id}")
    
    return {
        "id": None,
        "name": None,
        "email": email,
        "role": role,
        "status": "pending",
        "last_active_at": None
    }

async def resend_invite(db: AsyncSession, workspace_id: UUID, member_id: UUID) -> None:
    """Resend invite email. Since member_id is the user_id of the placeholder..."""
    member = await db.scalar(
        select(WorkspaceMember)
        .where(WorkspaceMember.workspace_id == workspace_id)
        .where(WorkspaceMember.user_id == member_id)
        .where(WorkspaceMember.status == "pending")
        .options(selectinload(WorkspaceMember.user))
    )
    if not member or not member.user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pending invite not found.")
        
    # TODO: Enqueue invite email
    print(f"[BACKGROUND] Re-sending invite email to {member.user.email} for workspace {workspace_id}")

async def update_member_role(db: AsyncSession, workspace_id: UUID, target_user_id: UUID, new_role: str, current_user_role: str) -> None:
    """
    Update a member's role.
    Rules:
    - Admin can only promote to Admin, Operator, Read-Only.
    - Only Owner can promote to Owner or change another Admin's role.
    - Cannot demote the last Owner.
    """
    if current_user_role != "owner" and new_role == "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owners can promote to owner.")
        
    member = await db.scalar(
        select(WorkspaceMember)
        .where(WorkspaceMember.workspace_id == workspace_id)
        .where(WorkspaceMember.user_id == target_user_id)
    )
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")
        
    if current_user_role != "owner" and member.role in ["owner", "admin"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owners can modify admin or owner roles.")
        
    # Prevent demoting last owner
    if member.role == "owner" and new_role != "owner":
        owner_count = await db.scalar(
            select(func.count(WorkspaceMember.id))
            .where(WorkspaceMember.workspace_id == workspace_id)
            .where(WorkspaceMember.role == "owner")
            .where(WorkspaceMember.status == "active")
        )
        if owner_count <= 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot demote the last owner of the workspace.")
            
    member.role = new_role
    await db.commit()

async def remove_member(db: AsyncSession, workspace_id: UUID, target_user_id: UUID) -> None:
    """
    Remove a member from the workspace.
    Cannot remove the last owner.
    """
    member = await db.scalar(
        select(WorkspaceMember)
        .where(WorkspaceMember.workspace_id == workspace_id)
        .where(WorkspaceMember.user_id == target_user_id)
    )
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")
        
    # Prevent removing last owner
    if member.role == "owner":
        owner_count = await db.scalar(
            select(func.count(WorkspaceMember.id))
            .where(WorkspaceMember.workspace_id == workspace_id)
            .where(WorkspaceMember.role == "owner")
            .where(WorkspaceMember.status == "active")
        )
        if owner_count <= 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot remove the last owner of the workspace.")
            
    await db.delete(member)
    await db.commit()
