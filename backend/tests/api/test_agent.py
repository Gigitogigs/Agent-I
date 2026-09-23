import pytest
from uuid import uuid4
from backend.db.models.workspace import Workspace
from backend.db.models.workspace_member import WorkspaceMember
from backend.db.models.user import User

from backend.core.security import create_access_token

async def setup_test_workspace(db_session):
    ws = Workspace(name="API Test Workspace")
    db_session.add(ws)
    await db_session.flush()

    user = User(email=f"user_{uuid4().hex[:8]}@example.com", password_hash="hash")
    db_session.add(user)
    await db_session.flush()
    
    member = WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="admin", status="active")
    db_session.add(member)
    await db_session.flush()
    
    token = create_access_token(str(user.id))
    await db_session.commit()
    return str(ws.id), token

@pytest.mark.asyncio
async def test_agent_api_key_update(async_client, db_session):
    ws_id, token = await setup_test_workspace(db_session)
    headers = {"Authorization": f"Bearer {token}"}

    
    # Happy path: Update API Key
    payload = {
        "apiKey": "sk-ant-testkey12345",
        "provider": "anthropic"
    }
    res = await async_client.put(f"/workspaces/{ws_id}/agents/orchestrator/api-key", json=payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["apiKeyHint"] is not None

@pytest.mark.asyncio
async def test_agent_config_update(async_client, db_session):
    ws_id, token = await setup_test_workspace(db_session)
    headers = {"Authorization": f"Bearer {token}"}
    
    # Update orchestrator config
    payload = {
        "model": "claude-3-5-sonnet-20240620",
        "tools": ["route_request"],
        "guardrails": {"pii": True},
        "hitlBreakpoints": [
            {"id": "b1", "label": "Test Breakpoint", "expiryBehavior": "auto-escalate", "slaWindowMins": 30}
        ]
    }
    res = await async_client.patch(f"/workspaces/{ws_id}/agents/orchestrator", json=payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["orchestrator"]["model"] == "claude-3-5-sonnet-20240620"
    assert "route_request" in data["orchestrator"]["tools"]
    assert data["orchestrator"]["hitlBreakpoints"][0]["id"] == "b1"

@pytest.mark.asyncio
async def test_agent_config_get(async_client, db_session):
    ws_id, token = await setup_test_workspace(db_session)
    headers = {"Authorization": f"Bearer {token}"}
    
    res = await async_client.get(f"/workspaces/{ws_id}/agents", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "global" in data
    assert "orchestrator" in data

@pytest.mark.asyncio
async def test_agent_api_unauthorized_missing_workspace(async_client, db_session):
    ws_id, token = await setup_test_workspace(db_session)
    headers = {"Authorization": f"Bearer {token}"}
    invalid_ws_id = str(uuid4())
    res = await async_client.get(f"/workspaces/{invalid_ws_id}/agents", headers=headers)
    assert res.status_code == 404
