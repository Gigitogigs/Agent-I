# rag/pgvector_client.py
#
# pgvector client — the low-level interface to the PostgreSQL vector store.
#
# Responsibility:
#   Provides the primitives the FAQ/RAG Agent uses to store and query
#   document embeddings. This is the "long-term knowledge" layer of the system,
#   as opposed to checkpointer.py which handles short-term working/session memory.
#
# Core operations this module exposes:
#   - upsert_chunks(chunks)          — store embedded document chunks into the vector table
#   - similarity_search(query, top_k, filter)
#                                    — retrieve the top-k most semantically similar chunks
#                                      for a given query string (cosine distance via HNSW)
#   - delete_document(doc_id)        — remove all chunks belonging to a document
#                                      (used during KB re-ingestion / updates)
#
# Backing store:
#   PostgreSQL with the pgvector extension enabled.
#   The vector column uses an HNSW index for approximate nearest-neighbour
#   search at scale (see rag_schema.sql for index config).
#
# Embedding model:
#   OllamaEmbeddings — embeds queries at search time and documents at ingestion time.
#   Swap the model name via the EMBEDDING_MODEL env var without changing any other code.
#
# Usage context:
#   Called exclusively by the FAQ/RAG Agent (retrieval_agent) during a
#   similarity search, and by the ingestion pipeline when loading KB documents.
#   Not called by the Orchestrator or Action Agent directly.

import os
from typing import Optional

from langchain_ollama import OllamaEmbeddings
from langchain_postgres import PGVector
from langchain_core.documents import Document

# ---------------------------------------------------------------------------
# Shared setup — created once at import time and reused across all calls.
# ---------------------------------------------------------------------------

_EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "qwen3-embedding:0.6b")
_COLLECTION_NAME = os.getenv("RAG_COLLECTION", "documents")
_CONNECTION_STRING = os.getenv("DB_URL")  # e.g. postgresql+psycopg://user:pass@host/db
if _CONNECTION_STRING and _CONNECTION_STRING.startswith("postgres:"):
    if not _CONNECTION_STRING.startswith("postgres://"):
        _CONNECTION_STRING = _CONNECTION_STRING.replace("postgres:", "postgresql+psycopg://", 1)
    else:
        _CONNECTION_STRING = _CONNECTION_STRING.replace("postgres://", "postgresql+psycopg://", 1)

embeddings = OllamaEmbeddings(model=_EMBEDDING_MODEL, base_url="http://127.0.0.1:11434")

vector_store = PGVector(
    embeddings=embeddings,
    collection_name=_COLLECTION_NAME,
    connection=_CONNECTION_STRING,  # PGVector uses `connection=`, not `connection_string=`
    use_jsonb=True,
    engine_args={"connect_args": {"options": "-c search_path=rag"}},
)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def upsert_chunks(chunks: list[Document]) -> list[str]:
    """
    Store (or overwrite) a list of LangChain Document chunks in the vector store.

    Each Document should have:
        - page_content : str   — the raw text of the chunk
        - metadata     : dict  — at minimum {"doc_id": "<source url or path>"}

    Returns the list of IDs assigned by the vector store.
    """
    ids = vector_store.add_documents(chunks)
    return ids


def similarity_search(
    query: str,
    top_k: int = 5,
    filter: Optional[dict] = None,
) -> list[Document]:
    """
    Retrieve the top-k document chunks most semantically similar to `query`.

    Args:
        query  : The user's question or search string (plain text — embedded here).
        top_k  : How many chunks to return (default 5).
        filter : Optional metadata filter dict, e.g. {"category": "refunds"}.
                 Keys must match fields stored in the chunk's metadata.

    Returns:
        A list of LangChain Document objects, ordered by similarity (most similar first).
    """
    results = vector_store.similarity_search(query, k=top_k, filter=filter)
    return results


def delete_document(doc_id: str) -> None:
    """
    Delete all stored chunks that belong to the given document.

    Use this before re-ingesting an updated document to avoid duplicates.

    Args:
        doc_id : The source identifier (URL or file path) stored in chunk metadata
                 under the key "doc_id".
    """
    vector_store.delete(filter={"doc_id": doc_id})