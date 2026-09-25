import asyncio
import uuid
import json
import urllib.request
import urllib.error
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text

BASE_URL = "http://127.0.0.1:8000/api/v1"
DATABASE_URL = "postgresql+asyncpg://postgres:ForcaBarca%402026!@localhost:5432/support_system"

async def test_race_condition():
    print("Setting up data for concurrency test...")
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    req = urllib.request.Request(f"{BASE_URL}/auth/register", data=json.dumps({"email": email, "password": "password123", "full_name": "Test"}).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as res:
        user_data = json.loads(res.read().decode())
        user_id = user_data["id"]
        
    req = urllib.request.Request(f"{BASE_URL}/auth/login", data=json.dumps({"email": email, "password": "password123"}).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as res:
        token = json.loads(res.read().decode())["access_token"]
        
    # Now set up workspace and conversation
    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    ws_id = str(uuid.uuid4())
    conv_id = str(uuid.uuid4())
    async with async_session() as db:
        from backend.db.models.workspace import Workspace
        from backend.db.models.chat import Conversation
        from backend.db.models.workspace_member import WorkspaceMember
        ws = Workspace(id=uuid.UUID(ws_id), name="Race Workspace")
        member = WorkspaceMember(workspace_id=uuid.UUID(ws_id), user_id=uuid.UUID(user_id), role="owner", status="active")
        conv = Conversation(id=uuid.UUID(conv_id), workspace_id=uuid.UUID(ws_id), customer_identifier='test-customer', status='open', channel='widget', metadata_={})
        db.add(ws)
        await db.flush()
        db.add(member)
        db.add(conv)
        await db.commit()
    await engine.dispose()

def submit_message_sync(ws_id, conv_id, message, token):
    url = f"{BASE_URL}/workspaces/{ws_id}/conversations/{conv_id}/chat"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = json.dumps({"message": message}).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as res:
            return res.status, json.loads(res.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return 500, str(e)

async def test_race_condition():
    
    # Run 5 concurrent POST requests
    loop = asyncio.get_running_loop()
    tasks = [
        loop.run_in_executor(None, submit_message_sync, ws_id, conv_id, f"Concurrent Message {i}", token)
        for i in range(5)
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    success = 0
    errors = 0
    for i, res in enumerate(results):
        if isinstance(res, Exception):
            print(f"Task {i} failed: {res}")
            errors += 1
        else:
            status, data = res
            print(f"Task {i} returned status: {status}")
            if status != 200:
                print(f"  Error: {data}")
                errors += 1
            else:
                success += 1
                
    print(f"\nConcurrency Results: {success} succeeded, {errors} errors.")
    if errors > 0:
        print("BUG FOUND: Concurrency race condition caused requests to fail (likely unique constraint on turn_index).")
    else:
        # Check DB to see if turns have duplicate turn_indexes (if unique constraint is missing!)
        engine = create_async_engine(DATABASE_URL)
        async_session = async_sessionmaker(engine, expire_on_commit=False)
        async with async_session() as db:
            from backend.db.models.chat import ConversationTurn
            from sqlalchemy import select
            res = await db.execute(select(ConversationTurn).where(ConversationTurn.conversation_id == uuid.UUID(conv_id)))
            turns = res.scalars().all()
            indexes = [t.turn_index for t in turns]
            print(f"Turn indexes in DB: {indexes}")
            if len(set(indexes)) != len(indexes):
                print("BUG FOUND: turn_index has duplicates! Missing unique constraint and race condition in application code.")

if __name__ == "__main__":
    asyncio.run(test_race_condition())
