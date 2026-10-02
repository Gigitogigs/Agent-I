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

@pytest.mark.asyncio
async def test_invalid_integration_type(async_client, db_session):
    ws_id, token = await setup_test_workspace(db_session)
    headers = {"Authorization": f"Bearer {token}"}
    
    payload = {
        "integration_type": "not_a_real_type",
        "name": "Invalid",
        "config": {"foo": "bar"}
    }
    create_res = await async_client.post(f"/workspaces/{ws_id}/settings/integrations", json=payload, headers=headers)
    assert create_res.status_code == 422

@pytest.mark.asyncio
async def test_connector_catalog_route(async_client, db_session):
    ws_id, token = await setup_test_workspace(db_session)
    headers = {"Authorization": f"Bearer {token}"}

    # Add a mock shopify integration
    payload = {
        "integration_type": "shopify",
        "name": "My Store",
        "config": {"store_url": "https://mystore.myshopify.com", "access_token": "shpat_123"}
    }
    await async_client.post(f"/workspaces/{ws_id}/settings/integrations", json=payload, headers=headers)

    res = await async_client.get(f"/workspaces/{ws_id}/settings/connector-catalog", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 4  # shopify, inhouse, zendesk, custom_mcp

    shopify = next(item for item in data if item["id"] == "shopify")
    assert shopify["is_configured"] is True
    assert shopify["integration_id"] is not None
    assert shopify["status"] == "pending"
    assert "order_account" in shopify["domains"]
    
    zendesk = next(item for item in data if item["id"] == "zendesk")
    assert zendesk["is_configured"] is False
    assert zendesk["integration_id"] is None

@pytest.mark.asyncio
async def test_is_primary_behavior(async_client, db_session):
    ws_id, token = await setup_test_workspace(db_session)
    headers = {"Authorization": f"Bearer {token}"}

    payload1 = {
        "integration_type": "shopify",
        "name": "My Store 1",
        "config": {"store_url": "https://store1.myshopify.com", "access_token": "shpat_123"}
    }
    res1 = await async_client.post(f"/workspaces/{ws_id}/settings/integrations", json=payload1, headers=headers)
    assert res1.status_code == 201
    id1 = res1.json()["id"]

    # First one is primary
    list_res = await async_client.get(f"/workspaces/{ws_id}/settings/integrations", headers=headers)
    int1 = next(i for i in list_res.json() if i["id"] == id1)
    assert int1["is_primary"] is True
    assert int1["domain"] == "order_account"

    # Add second with same domain
    payload2 = {
        "integration_type": "shopify",
        "name": "My Store 2",
        "config": {"store_url": "https://store2.myshopify.com", "access_token": "shpat_456"}
    }
    res2 = await async_client.post(f"/workspaces/{ws_id}/settings/integrations", json=payload2, headers=headers)
    assert res2.status_code == 201
    id2 = res2.json()["id"]

    # Second one is primary, first is not
    list_res = await async_client.get(f"/workspaces/{ws_id}/settings/integrations", headers=headers)
    
    # In list_res, check
    int1 = next(i for i in list_res.json() if i["id"] == id1)
    int2 = next(i for i in list_res.json() if i["id"] == id2)
    
    assert int1["is_primary"] is False
    assert int2["is_primary"] is True

@pytest.mark.asyncio
async def test_update_integration_config_and_name(async_client, db_session):
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

    update_payload = {
        "name": "My Store Updated",
        "config": {"store_url": "https://mystore.myshopify.com", "access_token": "shpat_456"}
    }
    update_res = await async_client.patch(f"/workspaces/{ws_id}/settings/integrations/{int_id}", json=update_payload, headers=headers)
    assert update_res.status_code == 200
    assert update_res.json()["name"] == "My Store Updated"
    assert update_res.json()["status"] == "pending"

@pytest.mark.asyncio
async def test_update_integration_is_primary_flip(async_client, db_session):
    ws_id, token = await setup_test_workspace(db_session)
    headers = {"Authorization": f"Bearer {token}"}

    payload1 = {
        "integration_type": "shopify",
        "name": "My Store 1",
        "config": {"store_url": "https://store1.myshopify.com", "access_token": "shpat_123"}
    }
    res1 = await async_client.post(f"/workspaces/{ws_id}/settings/integrations", json=payload1, headers=headers)
    id1 = res1.json()["id"]

    payload2 = {
        "integration_type": "shopify",
        "name": "My Store 2",
        "config": {"store_url": "https://store2.myshopify.com", "access_token": "shpat_456"}
    }
    res2 = await async_client.post(f"/workspaces/{ws_id}/settings/integrations", json=payload2, headers=headers)
    id2 = res2.json()["id"]

    # At this point, id2 is primary, id1 is not
    # Flip id1 back to primary
    update_res = await async_client.patch(f"/workspaces/{ws_id}/settings/integrations/{id1}", json={"is_primary": True}, headers=headers)
    assert update_res.status_code == 200

    list_res = await async_client.get(f"/workspaces/{ws_id}/settings/integrations", headers=headers)
    int1 = next(i for i in list_res.json() if i["id"] == id1)
    int2 = next(i for i in list_res.json() if i["id"] == id2)

    assert int1["is_primary"] is True
    assert int2["is_primary"] is False
