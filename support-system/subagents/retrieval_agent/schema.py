# subagents/retrieval_agent/schema.py
#
# Input / output schemas for the FAQ / RAG Agent.
#
# Responsibility:
#   Defines the Pydantic models that validate data flowing into and out of
#   the retrieval_agent, enforcing a strict contract between the Orchestrator
#   and the RAG pipeline.
#
# Expected schemas:
#
#   RetrievalRequest (input from Orchestrator):
#     - query           : str        — the customer's question (possibly
#                                      already rewritten by the Orchestrator)
#     - context_slice   : list[str]  — recent turns provided by the Orchestrator
#                                      for pronoun resolution / disambiguation
#     - top_k           : int        — number of chunks to retrieve (default: 5)
#     - filters         : dict | None — optional metadata filters (e.g. doc_type,
#                                      language, product_id) to narrow the search
#
#   RetrievalResult (output back to Orchestrator):
#     - answer          : str | None  — grounded answer text; None if confidence
#                                       is below threshold (see insufficient_coverage)
#     - source_chunks   : list[ChunkRef]  — list of chunk IDs + similarity scores
#                                           used to produce the answer (for citations
#                                           and audit trail)
#     - insufficient_coverage : bool  — True when retrieval confidence is too low;
#                                       signals the Orchestrator to escalate or
#                                       ask a clarifying question instead of
#                                       hallucinating an answer
#
#   ChunkRef:
#     - chunk_id        : str
#     - document_id     : str
#     - similarity      : float  — cosine similarity score from pgvector

from rag import pgvector_client, ingest
from pydantic import BaseModel


class RetrievalRequest(BaseModel):
    query: str
    context_slice: list[str]
    top_k: int = 5
    filters: dict | None = None

class ChunkRef(BaseModel):
    chunk_id: str
    document_id: str
    similarity: float

class RetrievalResult(BaseModel):
    answer: str | None = None
    source_chunks: list[ChunkRef] = []
    insufficient_coverage: bool = False