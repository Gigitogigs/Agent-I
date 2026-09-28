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
import json
from typing import Optional

from langchain_ollama import OllamaEmbeddings
from langchain_postgres import PGVector
from langchain_core.documents import Document

from backend.core.config import settings

# ---------------------------------------------------------------------------
# Shared setup — created once at import time and reused across all calls.
# ---------------------------------------------------------------------------

_EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "qwen3-embedding:0.6b")
_COLLECTION_NAME = os.getenv("RAG_COLLECTION", "documents")

# langchain_postgres PGVector prefers psycopg
_CONNECTION_STRING = settings.DATABASE_URL
if "asyncpg" in _CONNECTION_STRING:
    _CONNECTION_STRING = _CONNECTION_STRING.replace("asyncpg", "psycopg")

embeddings = OllamaEmbeddings(model=_EMBEDDING_MODEL, base_url="http://127.0.0.1:11434")

vector_store = PGVector(
    embeddings=embeddings,
    collection_name=_COLLECTION_NAME,
    connection=_CONNECTION_STRING,
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


def similarity_search_with_score(
    query: str,
    top_k: int = 5,
    filter: Optional[dict] = None,
) -> list[tuple[Document, float]]:
    """
    Retrieve top-k documents and their cosine distance scores.
    """
    return vector_store.similarity_search_with_score(query, k=top_k, filter=filter)


def keyword_search(
    query: str,
    top_k: int = 5,
    filter: Optional[dict] = None,
) -> list[Document]:
    """
    Retrieve chunks using BM25 / Full-Text Search.
    """
    from backend.db.session import get_legacy_sync_pool
    pool = get_legacy_sync_pool()
    docs = []
    
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) if hasattr(pool, 'row_factory') else conn.cursor() as cur:
            from psycopg.rows import dict_row
            # Ensure we use dict_row if not configured on pool
            if not hasattr(pool, 'row_factory'):
                cur.row_factory = dict_row

            where_clauses = ["fts @@ plainto_tsquery('english', %s)"]
            params = [query]
            
            if filter:
                for k, v in filter.items():
                    where_clauses.append("metadata @> %s::jsonb")
                    params.append(json.dumps({k: v}))
                    
            where_sql = " AND ".join(where_clauses)
            
            sql = f"""
                SELECT id, doc_id, content, metadata, 
                       ts_rank_cd(fts, plainto_tsquery('english', %s)) as rank
                FROM rag.documents
                WHERE {{where_sql}}
                ORDER BY rank DESC
                LIMIT %s
            """.replace('{where_sql}', where_sql)
            
            # The query string appears twice in the SQL (for filtering and ranking)
            params = [query] + params + [top_k]
            
            cur.execute(sql, params)
            for row in cur.fetchall():
                meta = row["metadata"] or {}
                meta["id"] = str(row["id"])
                meta["document_id"] = row["doc_id"]
                meta["fts_rank"] = float(row["rank"])
                docs.append(Document(page_content=row["content"], metadata=meta))
                
    return docs


def reciprocal_rank_fusion(
    dense_results: list[tuple[Document, float]],
    sparse_results: list[Document],
    k: int = 60
) -> list[Document]:
    """
    Merge dense and sparse results using Reciprocal Rank Fusion (RRF).
    """
    scores = {}
    docs = {}
    
    for rank, (doc, _) in enumerate(dense_results):
        doc_id = doc.metadata.get("id")
        if doc_id:
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
            docs[doc_id] = doc
            
    for rank, doc in enumerate(sparse_results):
        doc_id = doc.metadata.get("id")
        if doc_id:
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
            docs[doc_id] = doc
            
    # Sort by RRF score descending
    sorted_docs = []
    for doc_id, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
        doc = docs[doc_id]
        doc.metadata["rrf_score"] = score
        sorted_docs.append(doc)
        
    return sorted_docs


def delete_document(document_id: str) -> None:
    """
    Delete all stored chunks that belong to the given document.

    Use this before re-ingesting an updated document to avoid duplicates.

    Args:
        document_id : The source identifier stored in chunk metadata
    """
    vector_store.delete(filter={"document_id": document_id})