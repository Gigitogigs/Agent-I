from sqlalchemy import Column, String, Float, Boolean, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime, timezone
from backend.db.base import Base

class WorkspaceProviderKey(Base):
    __tablename__ = "workspace_provider_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String, nullable=False)
    encrypted_api_key = Column(String, nullable=False)
    key_hint = Column(String, nullable=True)
    is_verified = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("workspace_id", "provider", name="uix_workspace_provider"),
    )

class WorkspaceAgentConfig(Base):
    __tablename__ = "workspace_agent_config"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, unique=True)
    active_provider = Column(String, nullable=False)
    mode = Column(String, nullable=False, default="global")
    global_model = Column(String, nullable=True)
    global_temperature = Column(Float, nullable=False, default=0.7)
    global_system_prompt = Column(String, nullable=True)
    custom_models = Column(JSONB, nullable=True)
    custom_temperatures = Column(JSONB, nullable=True)
    custom_prompts = Column(JSONB, nullable=True)
    custom_tools = Column(JSONB, nullable=True)
    custom_guardrails = Column(JSONB, nullable=True)
    custom_hitl_breakpoints = Column(JSONB, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
