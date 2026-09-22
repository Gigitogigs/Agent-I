from sqlalchemy import Column, String, Boolean, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime, timezone
from backend.db.base import Base

class WorkspaceNotificationChannel(Base):
    __tablename__ = "workspace_notification_channels"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    channel_type = Column(String, nullable=False)
    name = Column(String, nullable=False)
    config = Column(JSONB, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class WorkspaceNotificationSetting(Base):
    __tablename__ = "workspace_notification_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String, nullable=False)
    channel_id = Column(UUID(as_uuid=True), ForeignKey("workspace_notification_channels.id", ondelete="CASCADE"), nullable=False)
    is_enabled = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("workspace_id", "event_type", "channel_id", name="uix_workspace_event_channel"),
    )

class WorkspaceIntegration(Base):
    __tablename__ = "workspace_integrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    integration_type = Column(String, nullable=False)
    name = Column(String, nullable=False)
    config = Column(JSONB, nullable=False)
    status = Column(String, nullable=False, default="active")
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
