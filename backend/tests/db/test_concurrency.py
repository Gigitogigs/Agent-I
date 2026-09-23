import pytest
import asyncio
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from backend.core.config import settings
from backend.db.models.user import User
from backend.db.models.workspace import Workspace
from backend.db.models.workspace_member import WorkspaceMember

@pytest.mark.asyncio
async def test_unique_constraint_race_condition(db_session):
    """Test that concurrent inserts on unique constraint (uix_workspace_user) raise IntegrityError."""
    ws = Workspace(name="Race WS")
    user = User(email="race@test.com", password_hash="hash")
    db_session.add_all([ws, user])
    await db_session.flush()

    # Create a new engine/sessionmaker for concurrent connections
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    TestingSessionLocal = async_sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False
    )
    
    async def insert_member():
        async with TestingSessionLocal() as session:
            try:
                member = WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="admin")
                session.add(member)
                await session.commit()
                return True
            except IntegrityError:
                await session.rollback()
                return False

    # Run 5 concurrent inserts
    results = await asyncio.gather(*(insert_member() for _ in range(5)))
    
    # Exactly one should succeed, the rest should fail with IntegrityError (return False)
    successes = sum(1 for r in results if r is True)
    failures = sum(1 for r in results if r is False)
    
    assert successes == 1
    assert failures == 4
    
    await engine.dispose()

@pytest.mark.asyncio
async def test_connection_pool_exhaustion():
    """Test LangGraph psycopg_pool exhaustion handles queuing."""
    import backend.db.session
    import psycopg_pool
    
    pool = backend.db.session.get_legacy_sync_pool()
    assert isinstance(pool, psycopg_pool.ConnectionPool)
    
    # Max size is 5 in get_legacy_sync_pool
    # Let's acquire 5 connections to exhaust it
    conns = []
    for _ in range(5):
        conns.append(pool.getconn(timeout=1))
        
    # Attempting to get a 6th should block/timeout (we use timeout=0.1 to fail fast)
    with pytest.raises(psycopg_pool.PoolTimeout):
        pool.getconn(timeout=0.1)
        
    # Release them
    for conn in conns:
        pool.putconn(conn)
        
    # Should be able to get one now
    conn = pool.getconn(timeout=1)
    pool.putconn(conn)
