import pytest
import asyncio
from uuid import uuid4
from sqlalchemy import select
from backend.db.models.workspace import Workspace
from backend.db.models.workspace_member import WorkspaceMember
from backend.db.models.user import User
from backend.db.models.chat import Conversation, ConversationTurn
from sqlalchemy.exc import IntegrityError

from backend.core.security import create_access_token

async def setup_test_workspace_and_conversation(db_session):
    ws = Workspace(name="Race Test WS")
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
    
    token = create_access_token(str(user.id))
    await db_session.commit()
    return str(ws.id), str(conv.id), token

@pytest.mark.asyncio
async def test_chat_concurrency_race_condition(async_client, db_session):
    """
    Test that submitting multiple chat messages concurrently does not result 
    in duplicate turn_indexes or database corruption.
    """
    ws_id, conv_id, token = await setup_test_workspace_and_conversation(db_session)
    headers = {"Authorization": f"Bearer {token}"}
    
    from backend.main import app
    from backend.api.dependencies import get_db
    
    # We MUST clear the dependency override for get_db so each concurrent request
    # gets its own fresh database session from the pool. Otherwise, SQLAlchemy 
    # throws an SAWarning for concurrent operations on the same session.
    app.dependency_overrides.pop(get_db, None)
    
    # Since we use httpx AsyncClient, we can easily simulate concurrent HTTP requests
    payload = {"message": "Concurrent message!"}
    
    async def post_message(index):
        # We add an index to the payload just to differentiate requests if needed
        # In reality, the chat endpoint just takes `message`.
        return await async_client.post(
            f"/workspaces/{ws_id}/conversations/{conv_id}/chat",
            json={"message": f"Concurrent message {index}!"},
            headers=headers
        )
        
    # Send 5 concurrent requests
    # Note: If the API isn't protected against races, it might throw 500s or 
    # insert duplicate turn indices. A correct implementation either queues them, 
    # handles the constraint violation gracefully, or succeeds via transactions.
    # Currently LangGraph is executed in a background thread synchronously. 
    # But for the test, we just want to ensure DB integrity.
    
    responses = await asyncio.gather(*(post_message(i) for i in range(5)), return_exceptions=True)
    
    # We commit/rollback to see DB state
    await db_session.commit()
    
    # Check DB for duplicate turn indexes
    stmt = select(ConversationTurn).where(ConversationTurn.conversation_id == conv_id)
    result = await db_session.execute(stmt)
    turns = result.scalars().all()
    
    # There should be exactly two turns per successful request (1 user, 1 agent)
    # But primarily, the turn_index must be strictly unique!
    indexes = [t.turn_index for t in turns]
    
    assert len(indexes) == len(set(indexes)), f"Duplicate turn indexes found: {indexes}"
    
    # Ensure no request left the database in a crashed state.
    # Some might have failed (500) if LangGraph threads lock or DB unique constraints hit,
    # but the DB must remain consistent.
    # If the system handles it perfectly, they might all be queued and succeed.
    errors = [r for r in responses if isinstance(r, Exception)]
    assert len(errors) == 0, f"Exceptions occurred during requests: {errors}"
