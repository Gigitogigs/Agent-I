from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_current_user, get_db, require_role, require_min_role
from backend.api.schemas.auth import MessageResponse
from backend.api.schemas.settings import (
    NotificationChannelOut,
    NotificationChannelCreate,
    NotificationChannelUpdate,
    BillingDetailsOut,
    IntegrationOut,
    IntegrationCreate
)
from backend.api.schemas.connectors import ConnectorCatalogEntry
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
from backend.services.connector_service import list_connector_catalog
from backend.db.models.settings import WorkspaceNotificationChannel

router = APIRouter(prefix="/workspaces/{workspace_id}/settings", tags=["settings"])

# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

@router.get("/notifications", response_model=List[NotificationChannelOut])
async def list_notifications(
    workspace_id: UUID,
    db: AsyncSession = Depends(get_db),
    _membership = Depends(require_min_role("admin"))
):
    return await get_notification_channels(db, workspace_id)

@router.post("/notifications", response_model=NotificationChannelOut, status_code=status.HTTP_201_CREATED)
async def add_notification_channel(
    workspace_id: UUID,
    body: NotificationChannelCreate,
    db: AsyncSession = Depends(get_db),
    _membership = Depends(require_min_role("admin"))
):
    return await create_notification_channel(db, workspace_id, body.model_dump())

@router.put("/notifications/{channel_id}", response_model=NotificationChannelOut)
async def update_notification_channel_route(
    workspace_id: UUID,
    channel_id: UUID,
    body: NotificationChannelUpdate,
    db: AsyncSession = Depends(get_db),
    _membership = Depends(require_min_role("admin"))
):
    return await update_notification_channel(db, workspace_id, channel_id, body.model_dump(exclude_unset=True))

@router.post("/notifications/{channel_id}/test", response_model=MessageResponse)
async def test_notification_channel(
    workspace_id: UUID,
    channel_id: UUID,
    db: AsyncSession = Depends(get_db),
    _membership = Depends(require_min_role("admin")),
):
    """Send a one-off test notification to verify channel config is correct."""
    test_payload = {
        "session_id":    "test-session-000",
        "risk_level":    "LOW",
        "checkpoint_id": "test-checkpoint-000",
        "message":       "This is a test notification from Agent-I.",
    }
    # Fetch the specific channel and dispatch only to it
    channel = await db.scalar(
        select(WorkspaceNotificationChannel)
        .where(WorkspaceNotificationChannel.id == channel_id, WorkspaceNotificationChannel.workspace_id == workspace_id)
    )
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
        
    from backend.services.settings_service import _decrypt_cfg
    from backend.services.notification_dispatcher import PROVIDERS, ProviderEnum
    cfg = _decrypt_cfg(channel)
    try:
        PROVIDERS[ProviderEnum(channel.channel_type)](cfg, {"workspace_id": str(workspace_id), **test_payload})
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to send test notification: {exc}"
        )
    return MessageResponse(message="Test notification sent successfully.")

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

@router.get("/connector-catalog", response_model=List[ConnectorCatalogEntry])
async def list_connector_catalog_route(
    workspace_id: UUID,
    db: AsyncSession = Depends(get_db),
    _membership = Depends(require_min_role("admin"))
):
    return await list_connector_catalog(db, workspace_id)

@router.get("/integrations", response_model=List[IntegrationOut])
async def list_integrations(
    workspace_id: UUID,
    db: AsyncSession = Depends(get_db),
    _membership = Depends(require_min_role("admin"))
):
    return await get_integrations(db, workspace_id)

@router.post("/integrations", response_model=IntegrationOut, status_code=status.HTTP_201_CREATED)
async def add_integration(
    workspace_id: UUID,
    body: IntegrationCreate,
    db: AsyncSession = Depends(get_db),
    _membership = Depends(require_min_role("admin"))
):
    return await create_integration(db, workspace_id, body.model_dump())

@router.delete("/integrations/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_integration(
    workspace_id: UUID,
    integration_id: UUID,
    db: AsyncSession = Depends(get_db),
    _membership = Depends(require_min_role("admin"))
):
    await delete_integration(db, workspace_id, integration_id)

@router.post("/integrations/{integration_id}/verify", response_model=MessageResponse)
async def verify_integration_route(
    workspace_id: UUID,
    integration_id: UUID,
    db: AsyncSession = Depends(get_db),
    _membership = Depends(require_min_role("admin"))
):
    res = await verify_integration(db, workspace_id, integration_id)
    return MessageResponse(message=res["message"])
