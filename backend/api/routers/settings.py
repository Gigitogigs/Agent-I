from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_current_user, get_db, require_role
from backend.api.schemas.auth import MessageResponse
from backend.api.schemas.settings import (
    NotificationChannelOut,
    NotificationChannelCreate,
    NotificationChannelUpdate,
    BillingDetailsOut,
    IntegrationOut,
    IntegrationCreate
)
from backend.db.models.user import User
from backend.services.settings_service import (
    get_notification_channels,
    create_notification_channel,
    update_notification_channel,
    get_billing_details,
    get_integrations,
    create_integration,
    delete_integration,
    verify_integration
)

router = APIRouter(prefix="/workspaces/{workspace_id}/settings", tags=["settings"])

# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

@router.get("/notifications", response_model=List[NotificationChannelOut])
async def list_notifications(
    workspace_id: UUID,
    db: AsyncSession = Depends(get_db),
    _membership = Depends(require_role("admin"))
):
    return await get_notification_channels(db, workspace_id)

@router.post("/notifications", response_model=NotificationChannelOut, status_code=status.HTTP_201_CREATED)
async def add_notification_channel(
    workspace_id: UUID,
    body: NotificationChannelCreate,
    db: AsyncSession = Depends(get_db),
    _membership = Depends(require_role("admin"))
):
    return await create_notification_channel(db, workspace_id, body.model_dump())

@router.put("/notifications/{channel_id}", response_model=NotificationChannelOut)
async def update_notification_channel_route(
    workspace_id: UUID,
    channel_id: UUID,
    body: NotificationChannelUpdate,
    db: AsyncSession = Depends(get_db),
    _membership = Depends(require_role("admin"))
):
    return await update_notification_channel(db, workspace_id, channel_id, body.model_dump(exclude_unset=True))

# ---------------------------------------------------------------------------
# Billing
# ---------------------------------------------------------------------------

@router.get("/billing", response_model=BillingDetailsOut)
async def get_billing(
    workspace_id: UUID,
    db: AsyncSession = Depends(get_db),
    _membership = Depends(require_role("owner"))
):
    return await get_billing_details(db, workspace_id)

# ---------------------------------------------------------------------------
# Integrations
# ---------------------------------------------------------------------------

@router.get("/integrations", response_model=List[IntegrationOut])
async def list_integrations(
    workspace_id: UUID,
    db: AsyncSession = Depends(get_db),
    _membership = Depends(require_role("admin"))
):
    return await get_integrations(db, workspace_id)

@router.post("/integrations", response_model=IntegrationOut, status_code=status.HTTP_201_CREATED)
async def add_integration(
    workspace_id: UUID,
    body: IntegrationCreate,
    db: AsyncSession = Depends(get_db),
    _membership = Depends(require_role("admin"))
):
    return await create_integration(db, workspace_id, body.model_dump())

@router.delete("/integrations/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_integration(
    workspace_id: UUID,
    integration_id: UUID,
    db: AsyncSession = Depends(get_db),
    _membership = Depends(require_role("admin"))
):
    await delete_integration(db, workspace_id, integration_id)

@router.post("/integrations/{integration_id}/verify", response_model=MessageResponse)
async def verify_integration_route(
    workspace_id: UUID,
    integration_id: UUID,
    db: AsyncSession = Depends(get_db),
    _membership = Depends(require_role("admin"))
):
    res = await verify_integration(db, workspace_id, integration_id)
    return MessageResponse(message=res["message"])
