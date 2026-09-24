import os
import asyncio
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, delete, text
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.session import async_session_maker

from backend.db.models.user import User
from backend.db.models.workspace import Workspace
from backend.db.models.workspace_member import WorkspaceMember
from backend.db.models.knowledge import Document
from backend.db.models.chat import Conversation, ConversationTurn
from backend.db.models.approvals import ApprovalRequest
# Assume document chunks are handled either via cascade or direct delete. 
# We'll rely on SQLAlchemy cascades if set up, or explicit deletes.

async def _hard_delete_workspace(db: AsyncSession, workspace: Workspace):
    """
    Executes the ordered hard deletion of a workspace as defined in the architecture.
    """
    print(f"[BACKGROUND] Hard deleting workspace {workspace.id}")
    
    # 1. Delete document chunks (pgvector). We execute raw SQL or use the client if needed.
    # Currently, pgvector chunks are handled by the langchain pgvector store.
    # Let's delete them via the pgvector client or raw SQL.
    await db.execute(text("DELETE FROM langchain_pg_embedding WHERE collection_id IN (SELECT uuid FROM langchain_pg_collection WHERE name = :ws_id)"), {"ws_id": str(workspace.id)})
    await db.execute(text("DELETE FROM langchain_pg_collection WHERE name = :ws_id"), {"ws_id": str(workspace.id)})
    
    # 2. Delete documents + remove files
    docs_result = await db.execute(select(Document).where(Document.workspace_id == workspace.id))
    docs = docs_result.scalars().all()
    for doc in docs:
        if doc.file_path and os.path.exists(doc.file_path):
            try:
                os.remove(doc.file_path)
            except Exception as e:
                print(f"[ERROR] Failed to remove file {doc.file_path}: {e}")
    await db.execute(delete(Document).where(Document.workspace_id == workspace.id))
    
    # 3. Delete conversation turns
    await db.execute(delete(ConversationTurn).where(ConversationTurn.conversation_id.in_(
        select(Conversation.id).where(Conversation.workspace_id == workspace.id)
    )))
    
    # 4. Delete conversations
    await db.execute(delete(Conversation).where(Conversation.workspace_id == workspace.id))
    
    # 5. Delete approval requests
    await db.execute(delete(ApprovalRequest).where(ApprovalRequest.workspace_id == workspace.id))
    
    # 6. Delete workspace members
    await db.execute(delete(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace.id))
    
    # 7. Delete workspace itself
    await db.execute(delete(Workspace).where(Workspace.id == workspace.id))


async def run_deletion_cleanup():
    """
    Hourly cron job to clean up workspaces and users whose grace period has expired.
    """
    print("[BACKGROUND] Running hourly deletion cleanup job...")
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=48)
    
    async with async_session_maker() as db:
        # --- Handle Workspace Deletions ---
        ws_stmt = select(Workspace).where(
            Workspace.deletion_scheduled_at != None,
            Workspace.deletion_scheduled_at <= cutoff_time
        )
        ws_result = await db.execute(ws_stmt)
        workspaces_to_delete = ws_result.scalars().all()
        
        for ws in workspaces_to_delete:
            try:
                await _hard_delete_workspace(db, ws)
                await db.commit()
            except Exception as e:
                await db.rollback()
                print(f"[ERROR] Failed to delete workspace {ws.id}: {e}")
                
        # --- Handle User/Account Deletions ---
        user_stmt = select(User).where(
            User.deletion_scheduled_at != None,
            User.deletion_scheduled_at <= cutoff_time
        )
        user_result = await db.execute(user_stmt)
        users_to_delete = user_result.scalars().all()
        
        for user in users_to_delete:
            try:
                # Delete any remaining workspace memberships where user is not an owner
                await db.execute(delete(WorkspaceMember).where(WorkspaceMember.user_id == user.id))
                
                # Delete the user itself
                await db.execute(delete(User).where(User.id == user.id))
                
                await db.commit()
                print(f"[BACKGROUND] Hard deleted user account {user.id}")
            except Exception as e:
                await db.rollback()
                print(f"[ERROR] Failed to delete user {user.id}: {e}")


# Initialize scheduler
scheduler = AsyncIOScheduler()

def start_scheduler():
    scheduler.add_job(run_deletion_cleanup, 'interval', hours=1, id='deletion_cleanup', replace_existing=True)
    # For testing purposes right now, let's also run it once immediately if needed, 
    # but we will just stick to the interval for production
    scheduler.start()
    print("[BACKGROUND] APScheduler started.")
