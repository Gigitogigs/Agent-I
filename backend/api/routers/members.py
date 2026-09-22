from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_current_user, get_db, require_role, require_min_role, get_current_membership
from backend.api.schemas.member import MemberOut, MemberInvite, MemberUpdate
from backend.api.schemas.auth import MessageResponse
from backend.db.models.user import User
from backend.db.models.workspace_member import WorkspaceMember
from backend.services.member_service import (
    get_workspace_members,
    invite_member,
    resend_invite,
    update_member_role,
    remove_member,
)

router = APIRouter(prefix="/workspaces/{workspace_id}/members", tags=["members"])

@router.get("", response_model=List[MemberOut])
async def list_members(
    workspace_id: UUID,
    db: AsyncSession = Depends(get_db),
    _membership = Depends(require_min_role("admin"))
):
    return await get_workspace_members(db, workspace_id)

@router.post("", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
async def new_member(
    workspace_id: UUID,
    body: MemberInvite,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _membership = Depends(require_min_role("admin"))
):
    return await invite_member(db, workspace_id, email=body.email, role=body.role, inviter=current_user)

@router.post("/{member_id}/resend-invite")
async def resend_member_invite(
    workspace_id: UUID,
    member_id: UUID,
    db: AsyncSession = Depends(get_db),
    _membership = Depends(require_min_role("admin"))
):
    await resend_invite(db, workspace_id, member_id)
    return MessageResponse(message="Invite resent.")

@router.patch("/{member_id}")
async def update_member(
    workspace_id: UUID,
    member_id: UUID,
    body: MemberUpdate,
    db: AsyncSession = Depends(get_db),
    membership: WorkspaceMember = Depends(require_min_role("admin"))
):
    await update_member_role(db, workspace_id, member_id, body.role, membership.role)
    return MessageResponse(message="Member role updated.")

@router.delete("/{member_id}")
async def delete_member(
    workspace_id: UUID,
    member_id: UUID,
    db: AsyncSession = Depends(get_db),
    _membership = Depends(require_role("owner"))
):
    await remove_member(db, workspace_id, member_id)
    return MessageResponse(message="Member removed.")
