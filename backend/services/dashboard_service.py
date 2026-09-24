import asyncio
from datetime import datetime, timezone, timedelta
from uuid import UUID

from sqlalchemy import select, func, desc, case
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models.approvals import ApprovalRequest
from backend.db.models.chat import Conversation
from backend.db.models.settings import WorkspaceIntegration

async def _get_urgent_approvals(db: AsyncSession, workspace_id: UUID) -> list:
    # Custom ordering for risk_level: critical > high > medium > low
    risk_order = case(
        (ApprovalRequest.risk_level == 'critical', 1),
        (ApprovalRequest.risk_level == 'high', 2),
        (ApprovalRequest.risk_level == 'medium', 3),
        (ApprovalRequest.risk_level == 'low', 4),
        else_=5
    )
    
    stmt = (
        select(ApprovalRequest)
        .where(
            ApprovalRequest.workspace_id == workspace_id,
            ApprovalRequest.status == 'pending'
        )
        .order_by(risk_order, ApprovalRequest.created_at.asc())
        .limit(3)
    )
    result = await db.execute(stmt)
    approvals = result.scalars().all()
    
    return [
        {
            "id": a.id,
            "action_type": a.action_type,
            "risk_level": a.risk_level,
            "created_at": a.created_at
        } for a in approvals
    ]

async def _get_headline_stats(db: AsyncSession, workspace_id: UUID) -> dict:
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Run these 3 simple aggregations in parallel as well for maximum speed
    async def count_conversations():
        stmt = select(func.count(Conversation.id)).where(
            Conversation.workspace_id == workspace_id,
            Conversation.created_at >= today_start
        )
        return await db.scalar(stmt) or 0
        
    async def count_escalations():
        stmt = select(func.count(ApprovalRequest.id)).where(
            ApprovalRequest.workspace_id == workspace_id,
            ApprovalRequest.status == 'pending'
        )
        return await db.scalar(stmt) or 0
        
    async def count_errors():
        stmt = select(func.count(WorkspaceIntegration.id)).where(
            WorkspaceIntegration.workspace_id == workspace_id,
            WorkspaceIntegration.status == 'failed'
        )
        return await db.scalar(stmt) or 0

    conv_count, esc_count, err_count = await asyncio.gather(
        count_conversations(),
        count_escalations(),
        count_errors()
    )
    
    return {
        "active_conversations_today": conv_count,
        "pending_escalations": esc_count,
        "unresolved_errors": err_count
    }

async def _get_recent_conversations(db: AsyncSession, workspace_id: UUID) -> list:
    stmt = (
        select(Conversation)
        .where(Conversation.workspace_id == workspace_id)
        .order_by(desc(Conversation.updated_at))
        .limit(5)
    )
    result = await db.execute(stmt)
    conversations = result.scalars().all()
    
    return [
        {
            "id": c.id,
            "preview": "Conversation snippet", # Optional: can be enriched later if turns are stored efficiently
            "status": c.status,
            "updated_at": c.updated_at
        } for c in conversations
    ]

async def _get_system_health(db: AsyncSession, workspace_id: UUID) -> dict:
    stmt = select(WorkspaceIntegration).where(
        WorkspaceIntegration.workspace_id == workspace_id,
        WorkspaceIntegration.status == 'failed'
    ).limit(1)
    
    failed_integration = await db.scalar(stmt)
    
    return {
        "integrations_status": "degraded" if failed_integration else "healthy"
    }

async def get_homepage_summary(db: AsyncSession, workspace_id: UUID) -> dict:
    """
    Executes all 4 dashboard queries in parallel using asyncio.gather.
    """
    approvals, stats, conversations, health = await asyncio.gather(
        _get_urgent_approvals(db, workspace_id),
        _get_headline_stats(db, workspace_id),
        _get_recent_conversations(db, workspace_id),
        _get_system_health(db, workspace_id)
    )
    
    return {
        "urgent_approvals": approvals,
        "stats": stats,
        "recent_conversations": conversations,
        "health": health
    }
