import asyncio
import os
import pytest
import psycopg
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from unittest.mock import AsyncMock

from backend.core.config import settings
from backend.db.base import Base
# Import all models to ensure they are registered with Base.metadata
from backend.db.models.user import User, UserSession
from backend.db.models.workspace import Workspace
from backend.db.models.workspace_member import WorkspaceMember
from backend.db.models.agent_config import WorkspaceProviderKey, WorkspaceAgentConfig
from backend.db.models.approvals import ApprovalRequest
from backend.db.models.chat import Conversation, ConversationTurn
from backend.db.models.knowledge import Document, DocumentChunk
from backend.db.models.settings import WorkspaceNotificationChannel, WorkspaceNotificationSetting, WorkspaceIntegration

TEST_DB_NAME = "support_system_test"

# Modify settings to point to the test db for any code that uses settings.DATABASE_URL
original_db_url = settings.DATABASE_URL
base_url = original_db_url.rsplit('/', 1)[0]
test_db_url = f"{base_url}/{TEST_DB_NAME}"
settings.DATABASE_URL = test_db_url

# We also need to configure the sync URL used by session.py
sync_base_url = base_url.replace("+asyncpg", "")
test_sync_db_url = f"{sync_base_url}/{TEST_DB_NAME}"
import backend.db.session
backend.db.session.SYNC_DB_URL = test_sync_db_url

def setup_test_db():
    conn_str = sync_base_url.replace("postgresql://", "postgresql://")
    conn_str += "/postgres" 
    
    try:
        with psycopg.connect(conn_str, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB_NAME}")
                cur.execute(f"CREATE DATABASE {TEST_DB_NAME}")
    except Exception as e:
        print(f"Failed to setup test DB: {e}")
        raise

    test_conn_str = f"{sync_base_url}/{TEST_DB_NAME}"
    with psycopg.connect(test_conn_str, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE SCHEMA IF NOT EXISTS checkpoints;")
            cur.execute("CREATE SCHEMA IF NOT EXISTS memory_store;")
            cur.execute("CREATE SCHEMA IF NOT EXISTS rag;")
            cur.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')


def teardown_test_db():
    if backend.db.session._checkpointer_pool:
        backend.db.session._checkpointer_pool.close()
    if backend.db.session._store_pool:
        backend.db.session._store_pool.close()
    if backend.db.session._legacy_pool:
        backend.db.session._legacy_pool.close()
        
    conn_str = sync_base_url + "/postgres"
    with psycopg.connect(conn_str, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT pg_terminate_backend(pg_stat_activity.pid)
                FROM pg_stat_activity
                WHERE pg_stat_activity.datname = '{TEST_DB_NAME}'
                  AND pid <> pg_backend_pid();
            """)
            cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB_NAME}")

@pytest.fixture(scope="session", autouse=True)
def setup_database():
    setup_test_db()
    
    engine = create_async_engine(test_db_url, echo=False)
    
    async def init_models():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
            from sqlalchemy import text
            await conn.execute(text("""
                CREATE OR REPLACE FUNCTION update_conversation_search_vector() RETURNS trigger AS $$
                BEGIN
                  NEW.search_vector := 
                    setweight(to_tsvector('english', coalesce(NEW.summary, '')), 'A') || 
                    setweight(to_tsvector('english', coalesce(NEW.customer_name, '')), 'B') || 
                    setweight(to_tsvector('english', coalesce(NEW.customer_identifier, '')), 'B');
                  RETURN NEW;
                END
                $$ LANGUAGE plpgsql;
            """))
            await conn.execute(text("""
                CREATE TRIGGER trg_conversation_search_vector
                BEFORE INSERT OR UPDATE OF summary, customer_name, customer_identifier
                ON conversations
                FOR EACH ROW
                EXECUTE FUNCTION update_conversation_search_vector();
            """))
            
    asyncio.run(init_models())
    
    yield
    
    async def dispose():
        await engine.dispose()
    asyncio.run(dispose())
    
    teardown_test_db()

@pytest.fixture
async def db_session():
    engine = create_async_engine(test_db_url, echo=False, pool_size=5, max_overflow=5)
    TestingSessionLocal = async_sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False
    )
    
    async with TestingSessionLocal() as session:
        yield session
        await session.rollback() 
        
    await engine.dispose()

@pytest.fixture(autouse=True)
def mock_arq_redis(monkeypatch):
    mock_pool = AsyncMock()
    # It might not be imported if running other tests, so we use try/except
    try:
        monkeypatch.setattr("backend.api.routers.knowledge.get_arq_redis", AsyncMock(return_value=mock_pool))
    except (ImportError, AttributeError):
        pass

@pytest.fixture
async def async_client(db_session):
    from backend.main import app
    from backend.api.dependencies import get_db
    from httpx import AsyncClient, ASGITransport
    
    # Override get_db to return the current test transaction
    async def override_get_db():
        yield db_session
        
    app.dependency_overrides[get_db] = override_get_db
    
    # Use httpx AsyncClient for integration testing
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as client:
        yield client
        
    app.dependency_overrides.clear()
