import asyncio
import urllib.request
import json
import urllib.error
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text
import sys

# We need the base URL and DB URL
BASE_URL = "http://127.0.0.1:8000/api/v1"
DATABASE_URL = "postgresql+asyncpg://postgres:ForcaBarca%402026!@localhost:5432/support_system"

def api_request(method, path, token=None, data=None):
    url = f"{BASE_URL}{path}"
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
        
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            res_body = response.read().decode()
            if res_body:
                return response.status, json.loads(res_body)
            return response.status, None
    except urllib.error.HTTPError as e:
        res_body = e.read().decode()
        print(f"HTTPError {e.code} on {method} {path}: {res_body}")
        try:
            return e.code, json.loads(res_body)
        except:
            return e.code, res_body
    except Exception as e:
        print(f"Error on {method} {path}: {e}")
        return 500, str(e)

async def insert_approval(workspace_id: str, status="pending") -> str:
    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    app_id = str(uuid.uuid4())
    conv_id = str(uuid.uuid4())
    
    async with async_session() as db:
        from backend.db.models.chat import Conversation
        from backend.db.models.approvals import ApprovalRequest
        
        conv = Conversation(
            id=uuid.UUID(conv_id),
            workspace_id=uuid.UUID(workspace_id),
            customer_identifier='test-customer',
            status='open',
            channel='widget',
            metadata_={}
        )
        app = ApprovalRequest(
            id=uuid.UUID(app_id),
            workspace_id=uuid.UUID(workspace_id),
            conversation_id=uuid.UUID(conv_id),
            agent_id='escalation_agent',
            action_type='refund',
            payload={"amount": 100},
            risk_level='HIGH',
            status=status
        )
        db.add(conv)
        await db.flush()
        db.add(app)
        await db.commit()
        
    await engine.dispose()
    return app_id

async def main():
    print("--- HITL Queue Tests ---")
    email = f"hitl_{uuid.uuid4().hex[:8]}@example.com"
    
    # 1. Register
    status_code, data = api_request("POST", "/auth/register", data={
        "email": email,
        "password": "password123",
        "full_name": "HITL Tester"
    })
    print(f"Register: {status_code}")
    if status_code not in (200, 201):
        print(f"Failed to register. Data: {data}")
        sys.exit(1)
    
    # 2. Login
    status_code, data = api_request("POST", "/auth/login", data={
        "email": email,
        "password": "password123"
    })
    print(f"Login: {status_code}")
    token = data["access_token"]
    
    # 3. Create Workspace
    status_code, data = api_request("POST", "/workspaces", token=token, data={
        "name": "HITL Workspace"
    })
    print(f"Create Workspace: {status_code}")
    workspace_id = data["id"]
    
    # 4. Insert approvals directly to DB (mimicking orchestrator)
    app1_id = await insert_approval(workspace_id, "pending")
    app2_id = await insert_approval(workspace_id, "pending")
    print(f"Inserted approvals: {app1_id}, {app2_id}")
    
    # 5. List approvals
    status_code, data = api_request("GET", f"/workspaces/{workspace_id}/approvals", token=token)
    print(f"List Approvals (All): {status_code} - Count: {len(data)}")
    assert len(data) == 2
    assert data[0]["status"] == "PENDING"
    
    # 6. Approve first request
    status_code, data = api_request("POST", f"/workspaces/{workspace_id}/approvals/{app1_id}/approve", token=token)
    print(f"Approve Request 1: {status_code} - {data}")
    assert status_code == 200
    
    # 7. Reject second request
    status_code, data = api_request("POST", f"/workspaces/{workspace_id}/approvals/{app2_id}/reject", token=token, data={"reason": "Too risky"})
    print(f"Reject Request 2: {status_code} - {data}")
    assert status_code == 200
    
    # 8. Verify statuses
    status_code, data = api_request("GET", f"/workspaces/{workspace_id}/approvals?status=APPROVED", token=token)
    print(f"List Approvals (APPROVED): Count {len(data)}")
    assert len(data) == 1
    assert data[0]["id"] == app1_id
    
    status_code, data = api_request("GET", f"/workspaces/{workspace_id}/approvals?status=REJECTED", token=token)
    print(f"List Approvals (REJECTED): Count {len(data)}")
    assert len(data) == 1
    assert data[0]["id"] == app2_id
    
    print("--- All Tests Passed! ---")

if __name__ == "__main__":
    asyncio.run(main())
