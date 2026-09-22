from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from backend.core.config import settings

# Create the async engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=20,
    max_overflow=10
)

# Create a sessionmaker
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False
)

# -----------------------------------------------------------------------------
# LangGraph Psycopg Connection Pools (Synchronous)
# -----------------------------------------------------------------------------
# LangGraph's checkpointer and store rely on synchronous `psycopg` (v3) connections.
# To prevent connection exhaustion, these are globally centralized here.
# Note: They cannot share a single pool because they require different schema search paths.

import psycopg_pool
from psycopg.rows import dict_row

SYNC_DB_URL = settings.DATABASE_URL.replace("+asyncpg", "")

# Pool for the Checkpointer (Conversations)
_checkpointer_pool = None
def get_checkpointer_pool() -> psycopg_pool.ConnectionPool:
    global _checkpointer_pool
    if _checkpointer_pool is None:
        _checkpointer_pool = psycopg_pool.ConnectionPool(
            conninfo=SYNC_DB_URL,
            min_size=1,
            max_size=10,
            kwargs={
                "autocommit": True,
                "prepare_threshold": 0,
                "options": "-c search_path=checkpoints",
                "row_factory": dict_row,
            },
        )
    return _checkpointer_pool


# Pool for the Cross-Session Memory Store
_store_pool = None
def get_store_pool() -> psycopg_pool.ConnectionPool:
    global _store_pool
    if _store_pool is None:
        _store_pool = psycopg_pool.ConnectionPool(
            conninfo=SYNC_DB_URL,
            min_size=1,
            max_size=10,
            kwargs={
                "autocommit": True,
                "prepare_threshold": 0,
                "options": "-c search_path=memory_store",
                "row_factory": dict_row,
            },
        )
    return _store_pool

# Pool for legacy psycopg2 / general sync tasks (defaults to public schema)
_legacy_pool = None
def get_legacy_sync_pool() -> psycopg_pool.ConnectionPool:
    global _legacy_pool
    if _legacy_pool is None:
        _legacy_pool = psycopg_pool.ConnectionPool(
            conninfo=SYNC_DB_URL,
            min_size=1,
            max_size=5,
            kwargs={
                "autocommit": True,
            },
        )
    return _legacy_pool
