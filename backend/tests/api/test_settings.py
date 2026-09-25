import pytest
from uuid import uuid4
from unittest.mock import AsyncMock
from backend.db.models.workspace import Workspace
from backend.db.models.user import User
from backend.db.models.workspace_member import WorkspaceMember
from backend.core.security import create_access_token

async def setup_test_workspace(db_session, role="admin"):
    ws = Workspace(name="Settings Test WS")
    db_session.add(ws)
    await db_session.flush()

    user = User(email=f"admin_{uuid4().hex[:8]}@example.com", password_hash="hash")
    db_session.add(user)
    await db_session.flush()
    
    member = WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=role, status="active")
    db_session.add(member)
    await db_session.flush()
    
    token = create_access_token(str(user.id))
    await db_session.commit()
    return str(ws.id), token

@pytest.mark.asyncio
async def test_notification_channels(async_client, db_session):
    ws_id, token = await setup_test_workspace(db_session)
    headers = {"Authorization": f"Bearer {token}"}
    
    payload = {
        "channel_type": "slack",
        "name": "General Notifications",
        "config": {"webhook_url": "https://hooks.slack.com/123"},
        "is_active": True,
        "on_escalation": True,
        "on_sla_breach": False
    }
    create_res = await async_client.post(f"/workspaces/{ws_id}/settings/notifications", json=payload, headers=headers)
    assert create_res.status_code == 201
    channel_id = create_res.json()["id"]
    
    update_payload = {
        "on_sla_breach": True
    }
    update_res = await async_client.put(f"/workspaces/{ws_id}/settings/notifications/{channel_id}", json=update_payload, headers=headers)
    assert update_res.status_code == 200
    assert update_res.json()["on_sla_breach"] is True
    
    list_res = await async_client.get(f"/workspaces/{ws_id}/settings/notifications", headers=headers)
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1

@pytest.mark.asyncio
async def test_billing_details(async_client, db_session):
    ws_id, token = await setup_test_workspace(db_session, role="owner")
    headers = {"Authorization": f"Bearer {token}"}
    
    res = await async_client.get(f"/workspaces/{ws_id}/settings/billing", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "plan_name" in data
    assert "usage" in data
    assert "invoices" in data

@pytest.mark.asyncio
async def test_integrations_crud(async_client, db_session):
    ws_id, token = await setup_test_workspace(db_session)
    headers = {"Authorization": f"Bearer {token}"}
    
    payload = {
        "integration_type": "shopify",
        "name": "My Store",
        "config": {"store_url": "https://mystore.myshopify.com", "access_token": "shpat_123"}
    }
    create_res = await async_client.post(f"/workspaces/{ws_id}/settings/integrations", json=payload, headers=headers)
    assert create_res.status_code == 201
    int_id = create_res.json()["id"]
    assert create_res.json()["status"] == "pending"
    
    list_res = await async_client.get(f"/workspaces/{ws_id}/settings/integrations", headers=headers)
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1
    
    del_res = await async_client.delete(f"/workspaces/{ws_id}/settings/integrations/{int_id}", headers=headers)
    assert del_res.status_code == 204
    
    list_res_after = await async_client.get(f"/workspaces/{ws_id}/settings/integrations", headers=headers)
    assert len(list_res_after.json()) == 0

@pytest.mark.asyncio
async def test_verify_integration_shopify(async_client, db_session, monkeypatch):
    ws_id, token = await setup_test_workspace(db_session)
    headers = {"Authorization": f"Bearer {token}"}
    
    payload = {
        "integration_type": "shopify",
        "name": "My Store",
        "config": {"store_url": "https://mystore.myshopify.com", "access_token": "shpat_123"}
    }
    create_res = await async_client.post(f"/workspaces/{ws_id}/settings/integrations", json=payload, headers=headers)
    int_id = create_res.json()["id"]
    
    class MockResponse:
        status_code = 200
    
    mock_get = AsyncMock(return_value=MockResponse())
    monkeypatch.setattr("httpx.AsyncClient.get", mock_get)
    
    verify_res = await async_client.post(f"/workspaces/{ws_id}/settings/integrations/{int_id}/verify", headers=headers)
    assert verify_res.status_code == 200
    
    monkeypatch.undo()
    list_res = await async_client.get(f"/workspaces/{ws_id}/settings/integrations", headers=headers)
    integration = next(i for i in list_res.json() if i["id"] == int_id)
    assert integration["status"] == "active"
