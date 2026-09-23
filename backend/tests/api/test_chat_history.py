import pytest
from uuid import uuid4
from backend.db.models.workspace import Workspace
from backend.db.models.chat import Conversation, ConversationTurn
from backend.db.models.user import User
from backend.db.models.workspace_member import WorkspaceMember

from backend.core.security import create_access_token

async def setup_test_workspace(db_session):
    ws = Workspace(name="History Test WS")
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
async def test_list_conversations_api(async_client, db_session):
    ws_id, token = await setup_test_workspace(db_session)
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create conversations
    c1 = Conversation(workspace_id=ws_id, customer_name="Alice", status="resolved")
    c2 = Conversation(workspace_id=ws_id, customer_name="Bob", status="escalated")
    db_session.add_all([c1, c2])
    await db_session.flush()
    
    # Test GET without filters
    res = await async_client.get(f"/workspaces/{ws_id}/conversations", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data["items"]) == 2
    
    # Test Status filter
    res = await async_client.get(f"/workspaces/{ws_id}/conversations?status=escalated", headers=headers)
    data = res.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["customer_name"] == "Bob"

@pytest.mark.asyncio
async def test_list_conversations_pagination(async_client, db_session):
    ws_id, token = await setup_test_workspace(db_session)
    headers = {"Authorization": f"Bearer {token}"}
    
    # Add 3 convs
    for i in range(3):
        db_session.add(Conversation(workspace_id=ws_id, customer_name=f"C{i}"))
    await db_session.flush()
    
    # Fetch with limit 2
    res = await async_client.get(f"/workspaces/{ws_id}/conversations?limit=2", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data["items"]) == 2
    assert data["nextCursor"] is not None
    
    # Fetch next page
    import urllib.parse
    cursor_encoded = urllib.parse.quote(data['nextCursor'])
    res_next = await async_client.get(f"/workspaces/{ws_id}/conversations?limit=2&cursor={cursor_encoded}", headers=headers)
    assert res_next.status_code == 200
    data_next = res_next.json()
    assert len(data_next["items"]) == 1
    assert data_next["nextCursor"] is None

@pytest.mark.asyncio
async def test_get_conversation_detail(async_client, db_session):
    ws_id, token = await setup_test_workspace(db_session)
    headers = {"Authorization": f"Bearer {token}"}
    
    c1 = Conversation(workspace_id=ws_id, customer_name="Alice")
    db_session.add(c1)
    await db_session.flush()
    
    t1 = ConversationTurn(conversation_id=c1.id, workspace_id=ws_id, turn_index=0, role="customer", content="Hi")
    db_session.add(t1)
    await db_session.flush()
    
    res = await async_client.get(f"/workspaces/{ws_id}/conversations/{c1.id}", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["customer_name"] == "Alice"
    assert len(data["transcript"]) == 1
    assert data["transcript"][0]["content"] == "Hi"

@pytest.mark.asyncio
async def test_get_conversation_not_found(async_client, db_session):
    ws_id, token = await setup_test_workspace(db_session)
    headers = {"Authorization": f"Bearer {token}"}
    invalid_ws_id = str(uuid4())
    invalid_c_id = str(uuid4())
    res = await async_client.get(f"/workspaces/{invalid_ws_id}/conversations/{invalid_c_id}", headers=headers)
    assert res.status_code == 404
