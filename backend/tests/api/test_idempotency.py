import pytest
import asyncio
from uuid import uuid4
from backend.db.models.workspace import Workspace
from backend.db.models.workspace_member import WorkspaceMember
from backend.db.models.user import User
from backend.db.models.chat import Conversation
from backend.db.models.approvals import ApprovalRequest
from backend.core.security import create_access_token

async def setup_test_workspace_and_conversation(db_session):
    ws = Workspace(name="Idempotency WS")
    db_session.add(ws)
    await db_session.flush()

    user = User(email=f"user_{uuid4().hex[:8]}@example.com", password_hash="hash")
    db_session.add(user)
    await db_session.flush()
    
    member = WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="admin", status="active")
    db_session.add(member)
    await db_session.flush()
    
    conv = Conversation(workspace_id=ws.id, status="open", channel="widget")
    db_session.add(conv)
    await db_session.flush()
    
    # Add a mock agent config so process_chat_turn doesn't crash on 'provider is None'
    from backend.db.models.agent_config import WorkspaceAgentConfig
    agent_config = WorkspaceAgentConfig(workspace_id=ws.id, active_provider="openai", global_model="gpt-4o")
    db_session.add(agent_config)
    await db_session.flush()
    
    token = create_access_token(str(user.id))
    await db_session.commit()
    return str(ws.id), str(conv.id), str(user.id), token

@pytest.mark.asyncio
async def test_chat_idempotency(async_client, db_session, mock_llm):
    # BUG: Chat endpoint does not currently implement Idempotency-Key handling, currently fails.
    ws_id, conv_id, _, token = await setup_test_workspace_and_conversation(db_session)
    headers = {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": f"test-key-{uuid4()}"
    }
    
    payload = {"message": "Hello, I need help"}
    
    # First request should execute normally
    res1 = await async_client.post(
        f"/workspaces/{ws_id}/conversations/{conv_id}/chat",
        json=payload,
        headers=headers
    )
    assert res1.status_code == 200, res1.text
    
    # Second request with the same Idempotency-Key should return the cached response
    # and NOT invoke the agent graph again.
    res2 = await async_client.post(
        f"/workspaces/{ws_id}/conversations/{conv_id}/chat",
        json=payload,
        headers=headers
    )
    assert res2.status_code == 200
    assert res1.json() == res2.json()

@pytest.mark.asyncio
async def test_approval_idempotency(async_client, db_session):
    # BUG: Approvals endpoints do not currently implement Idempotency-Key handling, currently fails.
    ws_id, conv_id, user_id, token = await setup_test_workspace_and_conversation(db_session)
    headers = {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": f"approve-key-{uuid4()}"
    }
    
    app_req = ApprovalRequest(
        workspace_id=ws_id,
        conversation_id=conv_id,
        agent_id="action_agent",
        action_type="refund",
        payload={"amount": 50},
        risk_level="high",
        status="pending"
    )
    db_session.add(app_req)
    await db_session.commit()
    await db_session.refresh(app_req)
    
    res1 = await async_client.post(
        f"/workspaces/{ws_id}/approvals/{app_req.id}/approve",
        headers=headers
    )
    assert res1.status_code == 200
    
    # Second request with the same Idempotency-Key should return 200 (idempotent success)
    # instead of a 409 Conflict.
    res2 = await async_client.post(
        f"/workspaces/{ws_id}/approvals/{app_req.id}/approve",
        headers=headers
    )
    assert res2.status_code == 200
