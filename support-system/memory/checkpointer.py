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
import psycopg_pool
from langgraph.checkpoint.postgres import PostgresSaver
import os
from dotenv import load_dotenv

load_dotenv(override=True)
DB_URL = os.getenv("DB_URL")


def get_checkpointer() -> PostgresSaver:
    """
    Create and return a LangGraph PostgresSaver checkpointer.

    Opens a psycopg2 connection to the Postgres database specified by the
    DB_URL environment variable, initialises the checkpointer schema (creates
    the required tables if they don't already exist), and returns the ready-
    to-use checkpointer instance.

    Returns:
        PostgresSaver: A LangGraph checkpointer that persists graph state to
        Postgres. Pass this directly to your compiled LangGraph graph:

            graph = builder.compile(checkpointer=get_checkpointer())

    Raises:
        psycopg.OperationalError: If the DB_URL is missing or the database
        is unreachable.
    """
    pool = psycopg_pool.ConnectionPool(
        conninfo=DB_URL,
        max_size=20,
        kwargs={
            "autocommit": True, 
            "prepare_threshold": 0,
        },
    )
    checkpointer = PostgresSaver(pool)
    checkpointer.setup()
    return checkpointer