from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_current_user, get_db, require_role
from backend.api.schemas.workspace import WorkspaceCreate, WorkspaceOut, PasswordConfirmBody
from backend.api.schemas.auth import MessageResponse
from backend.db.models.user import User
from backend.services.workspace_service import (
    get_user_workspaces,
    create_workspace,
    schedule_workspace_deletion,
    cancel_workspace_deletion,
)
from backend.services.dashboard_service import get_homepage_summary
from backend.api.schemas.dashboard import HomepageSummaryOut

router = APIRouter(prefix="/workspaces", tags=["workspaces"])

@router.get("", response_model=List[WorkspaceOut])
async def list_workspaces(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return await get_user_workspaces(db, current_user)

@router.post("", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
async def new_workspace(
    body: WorkspaceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return await create_workspace(db, name=body.name, user=current_user)

@router.delete("/{workspace_id}", status_code=status.HTTP_202_ACCEPTED)
async def delete_workspace(
    workspace_id: UUID,
    body: PasswordConfirmBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _membership = Depends(require_role("owner"))
):
    await schedule_workspace_deletion(db, workspace_id, current_user, body.password)
    return MessageResponse(message="Workspace scheduled for deletion. Check your email to confirm.")

@router.post("/{workspace_id}/cancel-deletion")
async def restore_workspace(
    workspace_id: UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
    _membership = Depends(require_role("owner"))
):
    await cancel_workspace_deletion(db, workspace_id)
    return MessageResponse(message="Workspace deletion cancelled.")

@router.get("/{workspace_id}/summary", response_model=HomepageSummaryOut)
async def get_dashboard_summary(
    workspace_id: UUID,
    db: AsyncSession = Depends(get_db),
    _membership = Depends(require_role("operator"))
):
    """
    Returns the composite BFF data payload for the workspace dashboard.
    """
    return await get_homepage_summary(db, workspace_id)
