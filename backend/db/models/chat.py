from sqlalchemy import Column, String, Integer, ForeignKey, DateTime, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB, TSVECTOR
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime, timezone
from backend.db.base import Base

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_identifier = Column(String, nullable=True)
    customer_name = Column(String, nullable=True)
    summary = Column(String, nullable=True)
    search_vector = Column(TSVECTOR, nullable=True)
    status = Column(String, nullable=False, default="open")
    channel = Column(String, nullable=False, default="widget")
    metadata_ = Column("metadata", JSONB, nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    turns = relationship("ConversationTurn", back_populates="conversation", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_conversations_workspace_id_status", "workspace_id", "status"),
        Index("ix_conversations_workspace_id_created_at", "workspace_id", "created_at"),
        Index("ix_conversations_search_vector", "search_vector", postgresql_using='gin'),
    )


class ConversationTurn(Base):
    __tablename__ = "conversation_turns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(UUID(as_uuid=True), nullable=False)
    turn_index = Column(Integer, nullable=False)
    role = Column(String, nullable=False)
    content = Column(String, nullable=True)
    agent_id = Column(String, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    conversation = relationship("Conversation", back_populates="turns")

    __table_args__ = (
        UniqueConstraint("conversation_id", "turn_index", name="uix_conversation_turn_index"),
        Index("ix_conversation_turns_workspace_created_at", "workspace_id", "created_at"),
    )
