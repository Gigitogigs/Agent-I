# memory/store.py
#
# Long-term memory store for the multi-agent support system.
#
# Responsibility:
#   Persist and retrieve cross-session facts about a customer — things like
#   preferences, past issue history, and resolved topics. This is distinct from
#   session memory (which is ephemeral per conversation) and from the pgvector
#   KB (which holds knowledge-base documents).
#
# Backing store:
#   - Postgres (structured facts, e.g. customer preferences table)
#   - pgvector (semantic recall — embed a customer fact so it can be retrieved
#     by meaning, not just exact lookup)
#
# Write pattern:
#   Written deliberately at the END of a conversation by the Orchestrator, not
#   on every turn. This keeps long-term memory high-signal and avoids storing
#   duplicate/noisy mid-conversation artifacts.
#
# Read pattern:
#   Read at the START of a conversation by the Orchestrator to assemble
#   personalised context before the first subagent call.
#
# Access permissions (per architecture spec):
#   - Orchestrator: read + write
#   - Subagents: no direct access (stateless; receive context slices via
#     the Orchestrator, not raw DB access)

import psycopg
import psycopg_pool
from psycopg.rows import dict_row
from langgraph.store.postgres import PostgresStore
import os
from dotenv import load_dotenv

load_dotenv(override=True)
DB_URL = os.getenv("DB_URL") or ""
_pool = None

def get_store():
    global _pool
    if _pool is None:
        _pool = psycopg_pool.ConnectionPool(
            conninfo=DB_URL,
            max_size=20,
            kwargs={
                "autocommit": True, 
                "prepare_threshold": 0,
                "row_factory": dict_row,
            },
        )
    store = PostgresStore(_pool)  # type: ignore[arg-type]
    store.setup()
    return store