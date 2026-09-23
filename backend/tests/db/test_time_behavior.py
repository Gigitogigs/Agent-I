import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from backend.db.models.user import User, UserSession
from backend.db.models.workspace import Workspace

@pytest.mark.asyncio
async def test_session_expiration_filtering(db_session):
    """Test that expired sessions can be correctly filtered based on timezone-aware dates."""
    user = User(email="time@test.com", password_hash="hash")
    db_session.add(user)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    
    # Session expired 1 hour ago
    expired_session = UserSession(
        user_id=user.id,
        refresh_token_hash="expired_hash",
        expires_at=now - timedelta(hours=1)
    )
    
    # Session expires in 1 hour
    active_session = UserSession(
        user_id=user.id,
        refresh_token_hash="active_hash",
        expires_at=now + timedelta(hours=1)
    )
    
    db_session.add_all([expired_session, active_session])
    await db_session.flush()

    # Query active sessions
    stmt = select(UserSession).where(
        UserSession.user_id == user.id,
        UserSession.expires_at > datetime.now(timezone.utc)
    )
    result = await db_session.execute(stmt)
    active_sessions = result.scalars().all()
    
    assert len(active_sessions) == 1
    assert active_sessions[0].refresh_token_hash == "active_hash"

@pytest.mark.asyncio
async def test_scheduled_deletion_retention(db_session):
    """Test the scheduled deletion flag works correctly with time ranges."""
    future_time = datetime.now(timezone.utc) + timedelta(days=30)
    past_time = datetime.now(timezone.utc) - timedelta(days=1)
    
    ws1 = Workspace(name="Keep", deletion_scheduled_at=future_time)
    ws2 = Workspace(name="Delete", deletion_scheduled_at=past_time)
    ws3 = Workspace(name="Active") # No deletion scheduled
    
    db_session.add_all([ws1, ws2, ws3])
    await db_session.flush()
    
    # Find workspaces ready for deletion (deletion_scheduled_at <= now)
    stmt = select(Workspace).where(
        Workspace.deletion_scheduled_at <= datetime.now(timezone.utc)
    )
    result = await db_session.execute(stmt)
    to_delete = result.scalars().all()
    
    assert len(to_delete) == 1
    assert to_delete[0].name == "Delete"
