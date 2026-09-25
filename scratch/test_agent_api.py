import sys
import os
import asyncio
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.db.session import get_legacy_sync_pool
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from backend.db.base import Base
from backend.db.models.workspace import Workspace
from backend.services.agent_service import get_agent_config, update_agent_config, update_api_key
from backend.api.schemas.agent import AgentConfigUpdate, HitlBreakpoint

# Assume the testing DB is the same. We use the async engine for testing.
from backend.db.session import engine

async_session_maker = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def test_agent_api():
    async with async_session_maker() as db:
        # Create a test workspace
        ws = Workspace(name="Agent API Test Workspace")
        db.add(ws)
        await db.commit()
        await db.refresh(ws)
        ws_id = ws.id
        
        try:
            print("1. Testing PUT /api-key")
            hint = await update_api_key(db, ws_id, "orchestrator", "sk-ant-testkey12345", "anthropic")
            print(f"   API Key hint returned: {hint}")
            
            print("\n2. Testing PATCH /agents/orchestrator")
            bp = HitlBreakpoint(id="b1", label="Test Breakpoint", expiryBehavior="auto-escalate", slaWindowMins=30)
            update = AgentConfigUpdate(
                model="claude-3-5-sonnet-20240620",
                tools=["route_request"],
                guardrails={"pii": True},
                hitlBreakpoints=[bp]
            )
            config_out = await update_agent_config(db, ws_id, "orchestrator", update)
            print(f"   Orchestrator Model: {config_out.orchestrator.model}")
            print(f"   Orchestrator Tools: {config_out.orchestrator.tools}")
            print(f"   Orchestrator Guardrails: {config_out.orchestrator.guardrails}")
            
            print("\n3. Testing GET /agents")
            config_out = await get_agent_config(db, ws_id)
            print(f"   Global Provider: {config_out.global_.provider}")
            print(f"   Global Hint: {config_out.global_.apiKeyHint}")
            print(f"   Orchestrator Tools: {config_out.orchestrator.tools}")
            print("Successfully tested agent APIs!")
            
        except Exception as e:
            print(f"Test failed with error: {e}")
            raise
        finally:
            # Clean up
            await db.delete(ws) # Cascade should delete agent configs
            await db.commit()

if __name__ == "__main__":
    asyncio.run(test_agent_api())
