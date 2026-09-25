import asyncio
import os
import sys
from uuid import uuid4
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from backend.db.session import engine
from backend.db.models.workspace import Workspace
from backend.db.models.chat import Conversation, ConversationTurn
from backend.services.chat_service import list_conversations, get_conversation_detail, update_conversation_summary

async_session_maker = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def test_conversation_api():
    async with async_session_maker() as db:
        # Create a test workspace
        ws = Workspace(name="Conversation API Test Workspace")
        db.add(ws)
        await db.commit()
        await db.refresh(ws)
        ws_id = ws.id
        
        try:
            print("1. Creating test conversations...")
            c1 = Conversation(workspace_id=ws_id, customer_name="Alice Smith", status="resolved")
            c2 = Conversation(workspace_id=ws_id, customer_name="Bob Jones", status="escalated")
            db.add_all([c1, c2])
            await db.commit()
            await db.refresh(c1)
            await db.refresh(c2)
            
            # Add turns to c1
            t1 = ConversationTurn(conversation_id=c1.id, workspace_id=ws_id, turn_index=0, role="customer", content="Help!")
            t2 = ConversationTurn(conversation_id=c1.id, workspace_id=ws_id, turn_index=1, role="agent", content="OK", agent_id="orchestrator")
            db.add_all([t1, t2])
            await db.commit()
            
            print("\n2. Testing update_conversation_summary...")
            await update_conversation_summary(db, ws_id, c1.id, "Alice needed help")
            
            # Flush so the trigger updates search_vector
            # We might need to refresh c1
            await db.refresh(c1)
            
            print("\n3. Testing list_conversations (no filter)...")
            res = await list_conversations(db, ws_id)
            print(f"   Found {len(res['items'])} conversations. Expected 2.")
            assert len(res['items']) == 2
            
            print("\n4. Testing list_conversations (status filter = escalated)...")
            res = await list_conversations(db, ws_id, status="escalated")
            print(f"   Found {len(res['items'])} conversations. Expected 1.")
            assert len(res['items']) == 1
            assert res['items'][0]['id'] == c2.id
            
            print("\n5. Testing list_conversations (search = Alice)...")
            res = await list_conversations(db, ws_id, search="Alice")
            print(f"   Found {len(res['items'])} conversations. Expected 1.")
            assert len(res['items']) == 1
            assert res['items'][0]['customer_name'] == "Alice Smith"
            assert res['items'][0]['summary'] == "Alice needed help"
            
            print("\n6. Testing list_conversations (search = help)...")
            res = await list_conversations(db, ws_id, search="help")
            print(f"   Found {len(res['items'])} conversations. Expected 1 (due to summary).")
            assert len(res['items']) == 1
            
            print("\n7. Testing get_conversation_detail...")
            detail = await get_conversation_detail(db, ws_id, c1.id)
            assert detail is not None
            print(f"   Transcript length: {len(detail['transcript'])}. Expected 2.")
            assert len(detail['transcript']) == 2
            print(f"   Agents involved: {detail['agentsInvolved']}. Expected ['orchestrator'].")
            assert detail['agentsInvolved'] == ['orchestrator']
            
            print("\nSuccessfully tested Conversation History APIs!")
            
        except Exception as e:
            print(f"\nTest failed with error: {e}")
            raise
        finally:
            # Clean up
            await db.delete(ws)
            await db.commit()

if __name__ == "__main__":
    asyncio.run(test_conversation_api())
