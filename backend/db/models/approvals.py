from sqlalchemy import Column, String, ForeignKey, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime, timezone
from backend.db.base import Base

class ApprovalRequest(Base):
    __tablename__ = "approval_requests"
    # Note: Alembic will create this in the public schema. We will migrate the old data manually.

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id = Column(String, nullable=False)
    action_type = Column(String, nullable=False)
    payload = Column(JSONB, nullable=False)
    risk_level = Column(String, nullable=False)
    reviewer_role = Column(String, nullable=True)
    status = Column(String, nullable=False, default="pending")
    operator_note = Column(String, nullable=True)
    resolved_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_approvals_workspace_id_status", "workspace_id", "status"),
        Index("ix_approvals_workspace_id_created_at", "workspace_id", "created_at"),
    )
