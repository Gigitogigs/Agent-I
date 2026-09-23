import pytest
import io
from uuid import uuid4
from backend.db.models.workspace import Workspace
from backend.db.models.workspace_member import WorkspaceMember
from backend.db.models.user import User

from backend.core.security import create_access_token

async def setup_test_workspace(db_session):
    ws = Workspace(name="Knowledge API Test Workspace")
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
async def test_knowledge_upload_and_delete(async_client, db_session):
    ws_id, token = await setup_test_workspace(db_session)
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. Upload file
    file_content = b"Autonomi return policy: 30 days with receipt."
    files = {"file": ("policy.txt", file_content, "text/plain")}
    
    res = await async_client.post(f"/workspaces/{ws_id}/knowledge-base/upload", files=files, headers=headers)
    assert res.status_code == 202
    data = res.json()
    assert "id" in data
    assert data["filename"] == "policy.txt"
    assert data["status"] == "processing"
    
    doc_id = data["id"]
    
    # 2. List documents
    res_list = await async_client.get(f"/workspaces/{ws_id}/knowledge-base", headers=headers)
    assert res_list.status_code == 200
    docs = res_list.json()
    assert len(docs) >= 1
    assert any(d["id"] == doc_id for d in docs)
    
    # 3. Delete document
    res_del = await async_client.delete(f"/workspaces/{ws_id}/knowledge-base/{doc_id}", headers=headers)
    assert res_del.status_code == 200
    
    # Verify deletion
    res_list_after = await async_client.get(f"/workspaces/{ws_id}/knowledge-base", headers=headers)
    docs_after = res_list_after.json()
    assert not any(d["id"] == doc_id for d in docs_after)

@pytest.mark.asyncio
async def test_knowledge_retrieval_empty(async_client, db_session):
    ws_id, token = await setup_test_workspace(db_session)
    headers = {"Authorization": f"Bearer {token}"}
    
    payload = {"query": "What is the policy?"}
    res = await async_client.post(f"/workspaces/{ws_id}/knowledge-base/test-retrieval", json=payload, headers=headers)
    
    # If the workspace has no docs, it should return 200 with empty results
    assert res.status_code == 200
    data = res.json()
    assert "results" in data
    assert len(data["results"]) == 0

@pytest.mark.asyncio
async def test_knowledge_upload_invalid_type(async_client, db_session):
    ws_id, token = await setup_test_workspace(db_session)
    headers = {"Authorization": f"Bearer {token}"}
    
    # Unsupported file type (e.g. random binary)
    file_content = b"\x00\x01\x02\x03"
    files = {"file": ("data.bin", file_content, "application/octet-stream")}
    
    # Assuming API rejects unknown types. If it accepts all, this will fail 
    # (which is a good finding for fortification).
    res = await async_client.post(f"/workspaces/{ws_id}/knowledge-base/upload", files=files, headers=headers)
    
    # Typically we'd expect 400 Bad Request. 
    # If the API allows it, this assert might fail and we can report it!
    assert res.status_code in [400, 415, 422], f"Expected rejection of bin file, got {res.status_code}"
