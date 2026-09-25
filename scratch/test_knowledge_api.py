import os
import sys
import uuid
import asyncio
import httpx

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from backend.core.config import settings

API_URL = "http://localhost:8000/api/v1"
# Assuming workspace is set up. We can just create one for testing.
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from backend.db.models.workspace import Workspace
from backend.db.models.workspace_member import WorkspaceMember

async def setup_test_workspace():
    engine = create_async_engine(settings.DATABASE_URL)
    AsyncSessionLocal = async_sessionmaker(bind=engine)
    async with AsyncSessionLocal() as db:
        # Check if workspace exists
        from sqlalchemy import select
        result = await db.execute(select(Workspace).limit(1))
        ws = result.scalar_one_or_none()
        if not ws:
            user_id = uuid.uuid4()
            ws = Workspace(name="Knowledge Test WS")
            db.add(ws)
            await db.flush()
            member = WorkspaceMember(workspace_id=ws.id, user_id=user_id, role="admin")
            db.add(member)
            await db.commit()
            print(f"Created workspace {ws.id}")
            return ws.id, user_id
        else:
            print(f"Using workspace {ws.id}")
            # Find its member
            result = await db.execute(select(WorkspaceMember).where(WorkspaceMember.workspace_id == ws.id).limit(1))
            member = result.scalar_one_or_none()
            user_id = member.user_id if member else uuid.uuid4()
            return ws.id, user_id

async def run_tests():
    ws_id, user_id = await setup_test_workspace()
    
    import tempfile
    
    # 1. Create a dummy file
    temp_dir = tempfile.gettempdir()
    test_file_path = os.path.join(temp_dir, "test_knowledge.txt")
    with open(test_file_path, "w") as f:
        f.write("Autonomi return policy: You can return items within 30 days of purchase with a receipt.")
        
    print("\n--- Testing Document Upload ---")
    async with httpx.AsyncClient(timeout=30) as client:
        # Upload
        with open(test_file_path, "rb") as f:
            files = {"file": ("test_knowledge.txt", f, "text/plain")}
            response = await client.post(f"{API_URL}/workspaces/{ws_id}/knowledge-base/upload", files=files)
            if response.status_code != 202:
                print(f"Upload Response {response.status_code}: {response.text}")
                return
            print(f"Upload Response {response.status_code}: {response.json()}")
            doc_id = response.json()["id"]
            
        print("\n--- Waiting for Processing ---")
        # In a real scenario, the ARQ worker needs to be running.
        # Here we just wait a bit and check the status. If ARQ worker isn't running, it will stay in processing.
        for _ in range(5):
            await asyncio.sleep(2)
            list_res = await client.get(f"{API_URL}/workspaces/{ws_id}/knowledge-base")
            docs = list_res.json()
            doc = next((d for d in docs if d["id"] == doc_id), None)
            if doc:
                print(f"Status: {doc['status']}")
                if doc['status'] == 'ready':
                    print("Processing completed successfully.")
                    break
                elif doc['status'] == 'failed':
                    print("Processing failed!")
                    break
                    
        print("\n--- Testing Retrieval ---")
        ret_res = await client.post(
            f"{API_URL}/workspaces/{ws_id}/knowledge-base/test-retrieval",
            json={"query": "What is the return policy?"}
        )
        print(f"Retrieval Response: {ret_res.status_code}")
        print(ret_res.json())

        print("\n--- Testing Deletion ---")
        del_res = await client.delete(f"{API_URL}/workspaces/{ws_id}/knowledge-base/{doc_id}")
        print(f"Deletion Response: {del_res.status_code} {del_res.json()}")

if __name__ == "__main__":
    asyncio.run(run_tests())
