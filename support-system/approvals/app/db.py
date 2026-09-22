# approvals/app/db.py
#
# Connection pool for the HITL Approval FastAPI application.
#
# Design note:
#   Using a ThreadedConnectionPool (psycopg2) rather than a module-level
#   singleton connection. A single shared _conn would break under:
#     - Postgres idle-timeout closing the connection
#     - Concurrent FastAPI requests hitting the same connection
#     - Process restarts / Postgres restarts
#
#   The pool is initialised once in FastAPI's lifespan event and torn down on
#   shutdown, so every request borrows a connection and returns it afterwards.

# approvals/app/db.py
#
# Connection wrapper for the HITL Approval FastAPI application.
# Now centralized to use the backend's shared legacy sync pool.

import psycopg
from backend.db.session import get_legacy_sync_pool

def init_pool(minconn: int = 2, maxconn: int = 10) -> None:
    """No-op. Pool is managed by backend/db/session.py lazily."""
    pass

def close_pool() -> None:
    """Close all connections. Called once from FastAPI lifespan on shutdown."""
    pool = get_legacy_sync_pool()
    pool.close()

def get_conn() -> psycopg.Connection:
    """Borrow a connection from the pool. Caller MUST call release_conn() after use."""
    pool = get_legacy_sync_pool()
    return pool.getconn()

def release_conn(conn: psycopg.Connection) -> None:
    """Return a borrowed connection to the pool."""
    pool = get_legacy_sync_pool()
    pool.putconn(conn)
