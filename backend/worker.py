import os
import sys
import asyncio
from typing import Dict, Any

# Ensure project root is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from arq import Worker
from arq.connections import RedisSettings
from backend.core.config import settings

# Import the task from the service
# We will create this task in backend/services/knowledge_service.py
from backend.services.knowledge_service import process_document_task
from langgraph.types import Command
import asyncio

async def resume_agent_graph(ctx: Dict[Any, Any], session_id: str, decision_payload: dict) -> None:
    """
    Executes the heavy LangGraph agent resume logic safely in the background.
    """
    try:
        from support_system.subagents.escalation_agent.graph import escalation_agent
        
        # We run the synchronous invoke inside asyncio.to_thread to prevent blocking the ARQ event loop
        await asyncio.to_thread(
            escalation_agent.invoke,
            Command(resume=decision_payload),
            {"configurable": {"thread_id": session_id, "checkpoint_id": ""}}
        )
        print(f"[INFO] Successfully resumed LangGraph for session {session_id}")
    except Exception as exc:
        print(f"[ERROR] Graph resume failed for session '{session_id}': {exc}")

async def startup(ctx: Dict[Any, Any]) -> None:
    """
    ARQ startup hook. Set up anything the worker needs (e.g. db connection pools).
    Since we use SQLAlchemy AsyncEngine globally in backend.db.session, 
    we just need to log that the worker started.
    """
    print("ARQ Worker started.")

async def shutdown(ctx: Dict[Any, Any]) -> None:
    """
    ARQ shutdown hook.
    """
    print("ARQ Worker shutting down.")

# Parse Redis URL from settings for ARQ
# redis://localhost:6379/0
redis_url = settings.REDIS_URL
host = "localhost"
port = 6379
database = 0

if "redis://" in redis_url:
    parts = redis_url.replace("redis://", "").split("/")
    host_port = parts[0].split(":")
    host = host_port[0]
    if len(host_port) > 1:
        port = int(host_port[1])
    if len(parts) > 1 and parts[1]:
        database = int(parts[1])

# ARQ Worker Settings
class WorkerSettings:
    functions = [process_document_task, resume_agent_graph]
    redis_settings = RedisSettings(host=host, port=port, database=database)
    on_startup = startup
    on_shutdown = shutdown
    # Automatically retry jobs on failure with exponential backoff
    max_tries = 3

if __name__ == "__main__":
    import arq
    import asyncio
    
    # Fix for Python 3.12+ where get_event_loop raises an error if no loop is running
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
        
    arq.run_worker(WorkerSettings)
