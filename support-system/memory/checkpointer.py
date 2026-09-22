"""
memory/checkpointer.py

Short-term / session memory layer for the multi-agent support system.

Responsibility:
    Provides a LangGraph-compatible checkpointer backed by PostgreSQL.
    The checkpointer persists the LangGraph state machine's conversation
    state (messages, context, intermediate results) between turns, enabling
    the Orchestrator Agent to resume a paused conversation (e.g. after a
    HITL approval) without losing context.

    This is distinct from rag/pgvector_client.py, which handles long-term
    knowledge retrieval (document embeddings). This module handles
    short-term working memory for a single conversation session.

Usage context:
    Instantiated once per conversation by the root/orchestrator agent and
    passed into the LangGraph graph as the `checkpointer` argument.
    Not called by subagents directly.
"""

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
import os
from dotenv import load_dotenv

from backend.db.session import get_checkpointer_pool

load_dotenv(override=True)
DB_URL = os.getenv("DB_URL") or ""
POSTGRES_CHECKPOINTER_SCHEMA = os.getenv("POSTGRES_CHECKPOINTER_SCHEMA", "checkpoints")
_pool = None


def setup_checkpointer() -> None:
    """
    Ensure the checkpointer tables exist.
    Called once by the application (or Orchestrator startup) to verify schema.
    """
    pass # No setup needed as the pool handles schema


def get_checkpointer() -> PostgresSaver:
    """
    Returns an instance of PostgresSaver initialized with the unified backend connection pool.
    """
    pool = get_checkpointer_pool()
    checkpointer = PostgresSaver(pool)
    checkpointer.setup()
    return checkpointer