import pytest
from uuid import uuid4
from datetime import datetime, timezone

from backend.db.models.workspace import Workspace
from backend.db.models.user import User
from backend.db.models.workspace_member import WorkspaceMember
from backend.db.models.chat import Conversation
from backend.db.models.approvals import ApprovalRequest
from backend.core.security import create_access_token
import backend.core.arq

@pytest.fixture(autouse=True)
def clear_arq_pool():
    backend.core.arq._pool = None
    yield
    backend.core.arq._pool = None

async def setup_test_workspace(db_session, role="operator"):
    ws = Workspace(name="Approvals Test WS")
    db_session.add(ws)
    await db_session.flush()

    user = User(email=f"operator_{uuid4().hex[:8]}@example.com", password_hash="hash")
    db_session.add(user)
    await db_session.flush()
    
    member = WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=role, status="active")
    db_session.add(member)
    await db_session.flush()
    
    conv = Conversation(workspace_id=ws.id, customer_name="Alice")
    db_session.add(conv)
    await db_session.flush()
    
    token = create_access_token(str(user.id))
    await db_session.commit()
    return str(ws.id), str(conv.id), str(user.id), token

@pytest.mark.asyncio
async def test_list_approvals(async_client, db_session):
    ws_id, conv_id, user_id, token = await setup_test_workspace(db_session)
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create an approval
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
    
    res = await async_client.get(f"/workspaces/{ws_id}/approvals", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 1
    assert data[0]["status"] == "PENDING"
    assert data[0]["action_type"] == "refund"

@pytest.mark.asyncio
async def test_approve_request(async_client, db_session):
    ws_id, conv_id, user_id, token = await setup_test_workspace(db_session)
    headers = {"Authorization": f"Bearer {token}"}
    
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
    
    # This should enqueue the job to ARQ real Redis
    res = await async_client.post(f"/workspaces/{ws_id}/approvals/{app_req.id}/approve", headers=headers)
    assert res.status_code == 200
    
    # Check DB update
    await db_session.refresh(app_req)
    assert app_req.status == "approved"
    assert str(app_req.resolved_by_user_id) == user_id

@pytest.mark.asyncio
async def test_reject_request(async_client, db_session):
    ws_id, conv_id, user_id, token = await setup_test_workspace(db_session)
    headers = {"Authorization": f"Bearer {token}"}
    
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
    
    payload = {"reason": "Not allowed by policy"}
    # This should enqueue the job to ARQ real Redis
    res = await async_client.post(f"/workspaces/{ws_id}/approvals/{app_req.id}/reject", json=payload, headers=headers)
    assert res.status_code == 200
    
    # Check DB update
    await db_session.refresh(app_req)
    assert app_req.status == "rejected"
    assert app_req.operator_note == "Not allowed by policy"
    assert str(app_req.resolved_by_user_id) == user_id

@pytest.mark.asyncio
async def test_approve_already_resolved(async_client, db_session):
    ws_id, conv_id, user_id, token = await setup_test_workspace(db_session)
    headers = {"Authorization": f"Bearer {token}"}
    
    app_req = ApprovalRequest(
        workspace_id=ws_id,
        conversation_id=conv_id,
        agent_id="action_agent",
        action_type="refund",
        payload={"amount": 50},
        risk_level="high",
        status="approved"
    )
    db_session.add(app_req)
    await db_session.commit()
    await db_session.refresh(app_req)
    
    res = await async_client.post(f"/workspaces/{ws_id}/approvals/{app_req.id}/approve", headers=headers)
    assert res.status_code == 409
