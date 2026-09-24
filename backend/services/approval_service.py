from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.db.models.approvals import ApprovalRequest
from backend.db.models.user import User

# Import LangGraph requirements
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from backend.core.arq import get_arq_redis
try:
    from langgraph.types import Command
    from support_system.subagents.escalation_agent.graph import escalation_agent
except ImportError as e:
    escalation_agent = None
    print(f"WARNING: escalation_agent could not be imported. Approvals will update the DB but graph resume will fail. Error: {e}")

async def list_approvals(db: AsyncSession, workspace_id: UUID, status_filter: Optional[str] = None) -> List[dict]:
    """Return all approval requests for a workspace, optionally filtered by status."""
    stmt = select(ApprovalRequest).where(ApprovalRequest.workspace_id == workspace_id)
    
    if status_filter and status_filter.upper() != "ALL":
        stmt = stmt.where(ApprovalRequest.status == status_filter.lower())
        
    stmt = stmt.order_by(ApprovalRequest.created_at.desc())
    
    result = await db.execute(stmt)
    approvals = result.scalars().all()
    
    # Map to the format expected by ApprovalOut
    # (FastAPI will automatically use aliases defined in ApprovalOut, but we need to resolve `resolvedBy` manually if we had joined users. 
    # For now, we'll return the DB model directly, and let Pydantic handle the fields, except `resolvedBy`.)
    
    out = []
    for a in approvals:
        model_dict = {
            "id": a.id,
            "status": a.status.upper(),
            "risk_level": a.risk_level,
            "action_type": a.action_type,
            "agent_id": a.agent_id,
            "conversation_id": a.conversation_id,
            "expires_at": a.expires_at,
            "created_at": a.created_at,
            "payload": a.payload,
            "resolved_at": a.resolved_at,
            "operator_note": a.operator_note,
            "resolvedBy": str(a.resolved_by_user_id) if a.resolved_by_user_id else None,
            "conversationSummary": None
        }
        out.append(model_dict)
    
    return out

async def approve_request(db: AsyncSession, workspace_id: UUID, app_id: UUID, current_user: User) -> None:
    """Approve a request and resume the LangGraph agent."""
    approval = await db.scalar(
        select(ApprovalRequest)
        .where(ApprovalRequest.id == app_id)
        .where(ApprovalRequest.workspace_id == workspace_id)
    )
    if not approval:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval request not found.")
        
    if approval.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Cannot approve: status is '{approval.status}'.")
        
    # Update DB record
    approval.status = "approved"
    approval.resolved_at = datetime.now(timezone.utc)
    approval.resolved_by_user_id = current_user.id
    
    await db.commit()
    
    # Enqueue ARQ task to resume LangGraph escalation agent
    redis = await get_arq_redis()
    await redis.enqueue_job(
        "resume_agent_graph", 
        session_id=str(approval.conversation_id), 
        decision_payload={
            "status": "approved",
            "operator_note": None,
            "resolved_by": current_user.email
        }
    )

async def reject_request(db: AsyncSession, workspace_id: UUID, app_id: UUID, reason: str, current_user: User) -> None:
    """Reject a request and enqueue an ARQ task to resume the LangGraph agent."""
    approval = await db.scalar(
        select(ApprovalRequest)
        .where(ApprovalRequest.id == app_id)
        .where(ApprovalRequest.workspace_id == workspace_id)
    )
    if not approval:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval request not found.")
        
    if approval.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Cannot reject: status is '{approval.status}'.")
        
    # Update DB record
    approval.status = "rejected"
    approval.resolved_at = datetime.now(timezone.utc)
    approval.resolved_by_user_id = current_user.id
    approval.operator_note = reason
    
    await db.commit()
    
    # Enqueue ARQ task to resume LangGraph escalation agent
    redis = await get_arq_redis()
    await redis.enqueue_job(
        "resume_agent_graph", 
        session_id=str(approval.conversation_id), 
        decision_payload={
            "status": "rejected",
            "operator_note": reason,
            "resolved_by": current_user.email
        }
    )
