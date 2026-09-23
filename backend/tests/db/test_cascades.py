import pytest
from sqlalchemy import select
from backend.db.models.user import User, UserSession
from backend.db.models.workspace import Workspace
from backend.db.models.workspace_member import WorkspaceMember
from backend.db.models.agent_config import WorkspaceAgentConfig, WorkspaceProviderKey
from backend.db.models.chat import Conversation, ConversationTurn

@pytest.mark.asyncio
async def test_workspace_deletion_cascade(db_session):
    """Test that deleting a Workspace cascades to its nested entities."""
    ws = Workspace(name="Cascade WS")
    user = User(email="cascade@test.com", password_hash="hash")
    db_session.add_all([ws, user])
    await db_session.flush()

    # Add related entities
    member = WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="admin")
    config = WorkspaceAgentConfig(workspace_id=ws.id, active_provider="ollama")
    key = WorkspaceProviderKey(workspace_id=ws.id, provider="ollama", encrypted_api_key="key")
    conv = Conversation(workspace_id=ws.id, status="open", channel="widget")
    
    db_session.add_all([member, config, key, conv])
    await db_session.flush()
    
    turn = ConversationTurn(
        conversation_id=conv.id, 
        workspace_id=ws.id, 
        turn_index=1, 
        role="user"
    )
    db_session.add(turn)
    await db_session.flush()

    # Delete workspace
    await db_session.delete(ws)
    await db_session.flush()

    # Verify cascades
    assert await db_session.scalar(select(WorkspaceMember).where(WorkspaceMember.id == member.id)) is None
    assert await db_session.scalar(select(WorkspaceAgentConfig).where(WorkspaceAgentConfig.id == config.id)) is None
    assert await db_session.scalar(select(WorkspaceProviderKey).where(WorkspaceProviderKey.id == key.id)) is None
    assert await db_session.scalar(select(Conversation).where(Conversation.id == conv.id)) is None
    assert await db_session.scalar(select(ConversationTurn).where(ConversationTurn.id == turn.id)) is None
    
    # User should remain
    assert await db_session.scalar(select(User).where(User.id == user.id)) is not None

@pytest.mark.asyncio
async def test_user_deletion_cascade(db_session):
    """Test that deleting a User cascades to their Sessions and WorkspaceMember links."""
    ws = Workspace(name="User Cascade WS")
    user = User(email="user_cascade@test.com", password_hash="hash")
    db_session.add_all([ws, user])
    await db_session.flush()

    session = UserSession(
        user_id=user.id, 
        refresh_token_hash="hash1",
        expires_at=ws.created_at # any valid datetime
    )
    member = WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="admin")
    db_session.add_all([session, member])
    await db_session.flush()

    # Delete User
    await db_session.delete(user)
    await db_session.flush()

    # Verify cascades
    assert await db_session.scalar(select(UserSession).where(UserSession.id == session.id)) is None
    assert await db_session.scalar(select(WorkspaceMember).where(WorkspaceMember.id == member.id)) is None
    
    # Workspace should remain
    assert await db_session.scalar(select(Workspace).where(Workspace.id == ws.id)) is not None
