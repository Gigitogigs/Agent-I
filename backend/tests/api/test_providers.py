import pytest
from uuid import uuid4
from unittest.mock import AsyncMock

from backend.db.models.workspace import Workspace
from backend.db.models.user import User
from backend.db.models.workspace_member import WorkspaceMember
from backend.core.security import create_access_token

async def setup_test_workspace(db_session, role="admin"):
    ws = Workspace(name="Providers Test WS")
    db_session.add(ws)
    await db_session.flush()

    user = User(email=f"user_{uuid4().hex[:8]}@example.com", password_hash="hash")
    db_session.add(user)
    await db_session.flush()
    
    member = WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=role, status="active")
    db_session.add(member)
    await db_session.flush()
    
    token = create_access_token(str(user.id))
    await db_session.commit()
    return str(ws.id), token

@pytest.mark.asyncio
async def test_get_providers(async_client, db_session):
    ws_id, token = await setup_test_workspace(db_session)
    headers = {"Authorization": f"Bearer {token}"}
    
    res = await async_client.get(f"/workspaces/{ws_id}/providers", headers=headers)
    assert res.status_code == 200
    data = res.json()
    
    assert len(data) > 0
    # Check ollama is there and verified
    ollama = next((p for p in data if p["id"] == "ollama"), None)
    assert ollama is not None
    assert ollama["isVerified"] is True
    
    anthropic = next((p for p in data if p["id"] == "anthropic"), None)
    assert anthropic is not None
    assert anthropic["isVerified"] is False

@pytest.mark.asyncio
async def test_update_api_key_success(async_client, db_session):
    ws_id, token = await setup_test_workspace(db_session)
    headers = {"Authorization": f"Bearer {token}"}
    
    payload = {"apiKey": "sk-ant-1234567890"}
    res = await async_client.put(f"/workspaces/{ws_id}/providers/anthropic/api-key", json=payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["apiKeyHint"] == "sk-a...7890"
    
    # Check if active provider is updated
    res2 = await async_client.get(f"/workspaces/{ws_id}/agents", headers=headers)
    assert res2.status_code == 200
    agent_data = res2.json()
    assert agent_data.get("orchestrator", {}).get("provider") == "anthropic"

@pytest.mark.asyncio
async def test_update_api_key_unsupported(async_client, db_session):
    ws_id, token = await setup_test_workspace(db_session)
    headers = {"Authorization": f"Bearer {token}"}
    
    payload = {"apiKey": "fake-key"}
    res = await async_client.put(f"/workspaces/{ws_id}/providers/unsupported/api-key", json=payload, headers=headers)
    assert res.status_code == 404

@pytest.mark.asyncio
async def test_update_api_key_no_key_required(async_client, db_session):
    ws_id, token = await setup_test_workspace(db_session)
    headers = {"Authorization": f"Bearer {token}"}
    
    payload = {"apiKey": "fake-key"}
    res = await async_client.put(f"/workspaces/{ws_id}/providers/ollama/api-key", json=payload, headers=headers)
    assert res.status_code == 400

@pytest.mark.asyncio
async def test_verify_provider_success(async_client, db_session, monkeypatch):
    ws_id, token = await setup_test_workspace(db_session)
    headers = {"Authorization": f"Bearer {token}"}
    
    payload = {"apiKey": "sk-ant-test"}
    await async_client.put(f"/workspaces/{ws_id}/providers/anthropic/api-key", json=payload, headers=headers)
    
    mock_model = AsyncMock()
    mock_model.ainvoke = AsyncMock(return_value=None)
    
    monkeypatch.setattr("backend.services.provider_service.build_model", lambda config: mock_model)
    
    res = await async_client.post(f"/workspaces/{ws_id}/providers/anthropic/verify", headers=headers)
    assert res.status_code == 200
    assert mock_model.ainvoke.called
    
    res2 = await async_client.get(f"/workspaces/{ws_id}/providers", headers=headers)
    anthropic = next((p for p in res2.json() if p["id"] == "anthropic"), None)
    assert anthropic["isVerified"] is True

@pytest.mark.asyncio
async def test_verify_provider_failure(async_client, db_session, monkeypatch):
    ws_id, token = await setup_test_workspace(db_session)
    headers = {"Authorization": f"Bearer {token}"}
    
    payload = {"apiKey": "sk-ant-test"}
    await async_client.put(f"/workspaces/{ws_id}/providers/anthropic/api-key", json=payload, headers=headers)
    
    mock_model = AsyncMock()
    mock_model.ainvoke.side_effect = Exception("API connection error")
    
    monkeypatch.setattr("backend.services.provider_service.build_model", lambda config: mock_model)
    
    res = await async_client.post(f"/workspaces/{ws_id}/providers/anthropic/verify", headers=headers)
    assert res.status_code == 400
    assert "API connection error" in res.json()["detail"]

@pytest.mark.asyncio
async def test_delete_api_key_active_provider(async_client, db_session):
    ws_id, token = await setup_test_workspace(db_session)
    headers = {"Authorization": f"Bearer {token}"}
    
    payload = {"apiKey": "sk-ant-test"}
    await async_client.put(f"/workspaces/{ws_id}/providers/anthropic/api-key", json=payload, headers=headers)
    
    res = await async_client.delete(f"/workspaces/{ws_id}/providers/anthropic/api-key", headers=headers)
    assert res.status_code == 409

@pytest.mark.asyncio
async def test_delete_api_key_success(async_client, db_session):
    ws_id, token = await setup_test_workspace(db_session)
    headers = {"Authorization": f"Bearer {token}"}
    
    await async_client.put(f"/workspaces/{ws_id}/providers/anthropic/api-key", json={"apiKey": "sk-ant-test"}, headers=headers)
    await async_client.put(f"/workspaces/{ws_id}/providers/openai/api-key", json={"apiKey": "sk-oai-test"}, headers=headers)
    
    res = await async_client.delete(f"/workspaces/{ws_id}/providers/anthropic/api-key", headers=headers)
    assert res.status_code == 200
