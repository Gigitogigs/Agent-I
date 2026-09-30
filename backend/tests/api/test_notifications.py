import pytest
import json
from uuid import UUID
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.models.settings import WorkspaceNotificationChannel
from backend.db.models.user import User

pytestmark = pytest.mark.asyncio

from backend.db.models.workspace import Workspace

@pytest.fixture
async def workspace_id(db_session: AsyncSession):
    ws = Workspace(name="Test WS")
    db_session.add(ws)
    await db_session.flush()
    return ws.id

from backend.core.security import create_access_token

from uuid import uuid4

@pytest.fixture
async def setup_auth(db_session: AsyncSession, workspace_id: UUID):
    user = User(email=f"test_{uuid4().hex[:8]}@test.com", password_hash="hash")
    db_session.add(user)
    await db_session.flush()
    
    from backend.db.models.workspace_member import WorkspaceMember
    member = WorkspaceMember(workspace_id=workspace_id, user=user, role="admin", status="active")
    db_session.add(member)
    await db_session.flush()
    await db_session.refresh(user, ["workspaces"])
    
    token = create_access_token(str(user.id))
    return {"Authorization": f"Bearer {token}"}

async def test_create_channel_encrypts_config(async_client: AsyncClient, db_session: AsyncSession, setup_auth: dict, workspace_id: UUID):
    payload = {
        "channel_type": "slack",
        "name": "My Slack Channel",
        "config": {"webhook_url": "https://example.invalid/slack-webhook-test-placeholder"},
        "is_active": True,
        "on_escalation": True,
        "on_sla_breach": True
    }
    
    response = await async_client.post(
        f"/api/v1/workspaces/{workspace_id}/settings/notifications",
        json=payload,
        headers=setup_auth
    )
    print("DEBUG RESPONSE:", response.status_code, response.text)
    assert response.status_code == 201
    
    data = response.json()
    channel_id = data["id"]
    
    # Assert DB row contains encrypted_payload, not the raw webhook_url
    channel = await db_session.scalar(
        select(WorkspaceNotificationChannel).where(WorkspaceNotificationChannel.id == UUID(channel_id))
    )
    assert channel is not None
    assert "webhook_url" not in channel.config
    assert "encrypted_payload" in channel.config
    
    from backend.services.settings_service import _decrypt_cfg
    # Verify we can decrypt it
    decrypted_config = _decrypt_cfg(channel)
    assert decrypted_config["webhook_url"] == payload["config"]["webhook_url"]

from unittest.mock import patch, MagicMock

async def test_dispatch_calls_correct_provider(db_session: AsyncSession, workspace_id: UUID):
    # Setup channel in DB
    channel = WorkspaceNotificationChannel(
        workspace_id=workspace_id,
        channel_type="slack",
        name="Test Slack",
        config={"encrypted_payload": "some_dummy_encryption"},
        is_active=True
    )
    db_session.add(channel)
    await db_session.flush()
    
    from backend.db.models.settings import WorkspaceNotificationSetting
    setting = WorkspaceNotificationSetting(
        workspace_id=workspace_id,
        event_type="escalation",
        channel_id=channel.id,
        is_enabled=True
    )
    db_session.add(setting)
    await db_session.flush()

    from backend.services.notification_dispatcher import PROVIDERS, ProviderEnum, dispatch
    mock_send_slack = MagicMock()
    with patch.dict(PROVIDERS, {ProviderEnum.slack: mock_send_slack}):
        with patch("backend.services.notification_dispatcher._decrypt_cfg", return_value={"webhook_url": "test_url"}):
            test_payload = {
                "session_id": "sess-123",
                "risk_level": "HIGH",
                "checkpoint_id": "chk-123",
                "message": "HITL required"
            }
            
            await dispatch("escalation", workspace_id, test_payload, db_session)
            
            # Assert mock was called
            mock_send_slack.assert_called_once_with(
                {"webhook_url": "test_url"}, 
                {"workspace_id": str(workspace_id), **test_payload}
            )

async def test_missing_config_keys_returns_422(async_client: AsyncClient, setup_auth: dict, workspace_id: UUID):
    payload = {
        "channel_type": "email",
        "name": "My Email Channel",
        "config": {"smtp_host": "smtp.mailgun.org"}, # Missing other keys
        "is_active": True,
        "on_escalation": True,
        "on_sla_breach": True
    }
    
    response = await async_client.post(
        f"/api/v1/workspaces/{workspace_id}/settings/notifications",
        json=payload,
        headers=setup_auth
    )
    assert response.status_code == 422
    assert "missing keys" in response.text

async def test_test_endpoint_fires_provider(async_client: AsyncClient, db_session: AsyncSession, setup_auth: dict, workspace_id: UUID):
    # Setup channel in DB
    channel = WorkspaceNotificationChannel(
        workspace_id=workspace_id,
        channel_type="discord",
        name="Test Discord",
        config={"encrypted_payload": "dummy"},
        is_active=True
    )
    db_session.add(channel)
    await db_session.flush()
    
    from backend.services.notification_dispatcher import PROVIDERS, ProviderEnum
    mock_discord = MagicMock()
    with patch("backend.services.settings_service._decrypt_cfg", return_value={"webhook_url": "test_url"}):
        with patch.dict(PROVIDERS, {ProviderEnum.discord: mock_discord}):
            response = await async_client.post(
                f"/api/v1/workspaces/{workspace_id}/settings/notifications/{channel.id}/test",
                headers=setup_auth
            )
            
            assert response.status_code == 200
            mock_discord.assert_called_once()
