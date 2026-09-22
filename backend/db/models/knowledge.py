from sqlalchemy import Column, String, Integer, ForeignKey, DateTime, Index, ARRAY
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime, timezone
from backend.db.base import Base

class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    uploaded_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="processing")
    error_message = Column(String, nullable=True)
    tags = Column(ARRAY(String), nullable=True)
    chunk_count = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_documents_workspace_id_status", "workspace_id", "status"),
    )

class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = ({"schema": "rag"})

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    content = Column(String, nullable=False)
    token_count = Column(Integer, nullable=True)
    langchain_embedding_id = Column(UUID(as_uuid=True), nullable=True) # Soft reference, no FK enforced
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
