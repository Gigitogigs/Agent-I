import os

models_dir = r"c:\Users\user\Documents\Agent-I\backend\db\models"

# 1. Update user.py to add UserSession
with open(os.path.join(models_dir, "user.py"), "w", encoding="utf-8") as f:
    f.write('''from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime, timezone
from backend.db.base import Base

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False, server_default="Unknown")
    password_hash = Column(String, nullable=False)
    reset_password_token = Column(String, nullable=True)
    reset_password_expires_at = Column(DateTime(timezone=True), nullable=True)
    avatar_url = Column(String, nullable=True)
    deletion_scheduled_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    workspaces = relationship("WorkspaceMember", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    refresh_token_hash = Column(String, nullable=False, unique=True)
    user_agent = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="sessions")
''')

# 2. Update workspace.py to match schema (add plan, stripe_customer_id, drop slug)
with open(os.path.join(models_dir, "workspace.py"), "w", encoding="utf-8") as f:
    f.write('''from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime, timezone
from backend.db.base import Base

class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    plan = Column(String, nullable=False, default="free")
    stripe_customer_id = Column(String, nullable=True)
    deletion_scheduled_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    members = relationship("WorkspaceMember", back_populates="workspace", cascade="all, delete-orphan")
''')

# 3. Update workspace_member.py (add invited_by_user_id)
with open(os.path.join(models_dir, "workspace_member.py"), "w", encoding="utf-8") as f:
    f.write('''from sqlalchemy import Column, String, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime, timezone
from backend.db.base import Base

class WorkspaceMember(Base):
    __tablename__ = "workspace_members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String, nullable=False) # owner, admin, operator, read-only
    invited_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    workspace = relationship("Workspace", back_populates="members")
    user = relationship("User", foreign_keys=[user_id], back_populates="workspaces")

    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uix_workspace_user"),
    )
''')

# 4. chat.py (Conversations & Turns)
with open(os.path.join(models_dir, "chat.py"), "w", encoding="utf-8") as f:
    f.write('''from sqlalchemy import Column, String, Integer, ForeignKey, DateTime, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime, timezone
from backend.db.base import Base

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_identifier = Column(String, nullable=True)
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
''')

# 5. approvals.py
with open(os.path.join(models_dir, "approvals.py"), "w", encoding="utf-8") as f:
    f.write('''from sqlalchemy import Column, String, ForeignKey, DateTime, Index
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
''')

# 6. knowledge.py
with open(os.path.join(models_dir, "knowledge.py"), "w", encoding="utf-8") as f:
    f.write('''from sqlalchemy import Column, String, Integer, ForeignKey, DateTime, Index, ARRAY
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
    document_id = Column(UUID(as_uuid=True), ForeignKey("public.documents.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    content = Column(String, nullable=False)
    token_count = Column(Integer, nullable=True)
    langchain_embedding_id = Column(UUID(as_uuid=True), nullable=True) # Soft reference, no FK enforced
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
''')

# 7. agent_config.py
with open(os.path.join(models_dir, "agent_config.py"), "w", encoding="utf-8") as f:
    f.write('''from sqlalchemy import Column, String, Float, Boolean, ForeignKey, DateTime, UniqueConstraint
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
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
''')

# 8. settings.py
with open(os.path.join(models_dir, "settings.py"), "w", encoding="utf-8") as f:
    f.write('''from sqlalchemy import Column, String, Boolean, ForeignKey, DateTime, UniqueConstraint
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
''')

# 9. __init__.py
with open(os.path.join(models_dir, "__init__.py"), "w", encoding="utf-8") as f:
    f.write('''from backend.db.base import Base
from backend.db.models.user import User, UserSession
from backend.db.models.workspace import Workspace
from backend.db.models.workspace_member import WorkspaceMember
from backend.db.models.chat import Conversation, ConversationTurn
from backend.db.models.approvals import ApprovalRequest
from backend.db.models.knowledge import Document, DocumentChunk
from backend.db.models.agent_config import WorkspaceProviderKey, WorkspaceAgentConfig
from backend.db.models.settings import WorkspaceNotificationChannel, WorkspaceNotificationSetting, WorkspaceIntegration
''')
