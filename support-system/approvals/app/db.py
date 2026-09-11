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

import psycopg2
from psycopg2 import pool as pg_pool
import os
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DB_URL")
if not DB_URL:
    raise RuntimeError("DB_URL environment variable is not set.")

# Module-level pool — created in lifespan, reused by all requests
_pool: pg_pool.ThreadedConnectionPool | None = None


def init_pool(minconn: int = 2, maxconn: int = 10) -> None:
    """Initialise the pool. Called once from FastAPI lifespan on startup."""
    global _pool
    _pool = pg_pool.ThreadedConnectionPool(minconn=minconn, maxconn=maxconn, dsn=DB_URL)


def close_pool() -> None:
    """Close all connections. Called once from FastAPI lifespan on shutdown."""
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None


def get_conn() -> psycopg2.extensions.connection:
    """Borrow a connection from the pool. Caller MUST call release_conn() after use."""
    if _pool is None:
        raise RuntimeError("DB pool not initialised — did FastAPI lifespan run?")
    return _pool.getconn()


def release_conn(conn: psycopg2.extensions.connection) -> None:
    """Return a borrowed connection to the pool."""
    if _pool is not None:
        _pool.putconn(conn)
