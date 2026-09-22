from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_current_user, get_db, require_min_role
from backend.api.schemas.approval import ApprovalOut, ApprovalRejectBody
from backend.api.schemas.auth import MessageResponse
from backend.db.models.user import User
from backend.services.approval_service import (
    list_approvals,
    approve_request,
    reject_request,
)

router = APIRouter(prefix="/workspaces/{workspace_id}/approvals", tags=["approvals"])

@router.get("", response_model=List[ApprovalOut])
async def get_approvals(
    workspace_id: UUID,
    status: Optional[str] = Query(None, description="Filter by status (PENDING, APPROVED, REJECTED, EXPIRED, CANCELLED, ALL)"),
    db: AsyncSession = Depends(get_db),
    _membership = Depends(require_min_role("operator"))
):
    return await list_approvals(db, workspace_id, status)

@router.post("/{app_id}/approve", status_code=status.HTTP_200_OK)
async def approve_approval(
    workspace_id: UUID,
    app_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _membership = Depends(require_min_role("operator"))
):
    await approve_request(db, workspace_id, app_id, current_user)
    return MessageResponse(message="Request approved successfully.")

@router.post("/{app_id}/reject", status_code=status.HTTP_200_OK)
async def reject_approval(
    workspace_id: UUID,
    app_id: UUID,
    body: ApprovalRejectBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _membership = Depends(require_min_role("operator"))
):
    await reject_request(db, workspace_id, app_id, body.reason, current_user)
    return MessageResponse(message="Request rejected successfully.")
