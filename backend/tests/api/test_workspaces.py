import pytest
from uuid import uuid4
from backend.db.models.workspace import Workspace
from backend.db.models.user import User
from backend.db.models.workspace_member import WorkspaceMember
from backend.core.security import create_access_token, hash_password

async def setup_test_user(db_session):
    password = "password123"
    password_hash = hash_password(password)
    user = User(email=f"user_{uuid4().hex[:8]}@example.com", password_hash=password_hash)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    token = create_access_token(str(user.id))
    return user, token, password

@pytest.mark.asyncio
async def test_create_workspace(async_client, db_session):
    user, token, _ = await setup_test_user(db_session)
    headers = {"Authorization": f"Bearer {token}"}
    
    payload = {"name": "New Test Workspace"}
    res = await async_client.post("/workspaces", json=payload, headers=headers)
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "New Test Workspace"
    assert data["role"] == "owner"
    assert data["deletion_scheduled_at"] is None

@pytest.mark.asyncio
async def test_list_workspaces(async_client, db_session):
    user, token, _ = await setup_test_user(db_session)
    headers = {"Authorization": f"Bearer {token}"}
    
    await async_client.post("/workspaces", json={"name": "Workspace 1"}, headers=headers)
    await async_client.post("/workspaces", json={"name": "Workspace 2"}, headers=headers)
    
    res = await async_client.get("/workspaces", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 2
    assert any(ws["name"] == "Workspace 1" for ws in data)

@pytest.mark.asyncio
async def test_schedule_workspace_deletion(async_client, db_session):
    user, token, password = await setup_test_user(db_session)
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create workspace directly in DB
    ws = Workspace(name="To Be Deleted")
    db_session.add(ws)
    await db_session.flush()
    member = WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner", status="active")
    db_session.add(member)
    await db_session.commit()
    ws_id = str(ws.id)
    
    res_wrong = await async_client.request("DELETE", f"/workspaces/{ws_id}", json={"password": "wrongpassword"}, headers=headers)
    assert res_wrong.status_code == 401
    
    res_correct = await async_client.request("DELETE", f"/workspaces/{ws_id}", json={"password": password}, headers=headers)
    assert res_correct.status_code == 202
    
    list_res = await async_client.get("/workspaces", headers=headers)
    ws = next(w for w in list_res.json() if w["id"] == ws_id)
    assert ws["deletion_scheduled_at"] is not None

@pytest.mark.asyncio
async def test_cancel_workspace_deletion(async_client, db_session):
    user, token, password = await setup_test_user(db_session)
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create workspace directly in DB
    ws = Workspace(name="To Be Restored")
    db_session.add(ws)
    await db_session.flush()
    member = WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner", status="active")
    db_session.add(member)
    await db_session.commit()
    ws_id = str(ws.id)
    
    await async_client.request("DELETE", f"/workspaces/{ws_id}", json={"password": password}, headers=headers)
    
    res_restore = await async_client.post(f"/workspaces/{ws_id}/cancel-deletion", headers=headers)
    assert res_restore.status_code == 200
    
    list_res = await async_client.get("/workspaces", headers=headers)
    ws = next(w for w in list_res.json() if w["id"] == ws_id)
    assert ws["deletion_scheduled_at"] is None
