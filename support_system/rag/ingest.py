# rag/ingest.py
#
# Ingestion pipeline — loads knowledge-base documents, splits them into
# chunks, and stores the chunks (with embeddings) in the vector store.
#
# Run this script whenever you add or update documents in your knowledge base:
#
#   python -m rag.ingest --docs knowledge_base/
#
# It is idempotent: existing chunks for a document are deleted before
# re-inserting, so running it twice won't create duplicates.

import os
import argparse
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from support_system.rag.pgvector_client import upsert_chunks, delete_document

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CHUNK_SIZE    = int(os.getenv("CHUNK_SIZE", "512"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "64"))

splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
)

SUPPORTED_EXTENSIONS = {".md", ".txt"}

# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------

def load_documents(docs_dir: str) -> list[Document]:
    """
    Walk `docs_dir` and load every .md / .txt file as a LangChain Document.

    Each document's metadata includes:
        - doc_id  : relative file path (used as the stable identifier)
        - source  : same as doc_id (LangChain convention)
    """
    docs = []
    for path in Path(docs_dir).rglob("*"):
        if path.suffix not in SUPPORTED_EXTENSIONS:
            continue
        doc_id = str(path.relative_to(docs_dir))
        text = path.read_text(encoding="utf-8")
        docs.append(Document(page_content=text, metadata={"doc_id": doc_id, "source": doc_id}))
    print(f"Loaded {len(docs)} document(s) from {docs_dir}")
    return docs


def split_documents(docs: list[Document]) -> list[Document]:
    """
    Split each document into smaller chunks for embedding.
    Metadata (including doc_id) is preserved on every chunk.
    """
    chunks = splitter.split_documents(docs)
    print(f"Split into {len(chunks)} chunk(s) "
          f"(chunk_size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP})")
    return chunks


def run(docs_dir: str) -> None:
    """
    Full ingestion pipeline: load → split → upsert.

    Deletes existing chunks for each document before re-inserting so the
    pipeline is safe to re-run after edits.
    """
    docs   = load_documents(docs_dir)
    chunks = split_documents(docs)

    # Group chunks by doc_id so we can delete-then-reinsert per document
    by_doc: dict[str, list[Document]] = {}
    for chunk in chunks:
        doc_id = chunk.metadata["doc_id"]
        by_doc.setdefault(doc_id, []).append(chunk)

    for doc_id, doc_chunks in by_doc.items():
        delete_document(doc_id)          # remove stale chunks (no-op on first run)
        upsert_chunks(doc_chunks)
        print(f"  ✓ {doc_id} — {len(doc_chunks)} chunk(s) indexed")

    print(f"\nDone. {len(chunks)} total chunk(s) stored in vector store.")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest knowledge-base documents into pgvector.")
    parser.add_argument(
        "--docs",
        default="knowledge_base",
        help="Path to the folder containing .md / .txt documents (default: knowledge_base/)",
    )
    args = parser.parse_args()
    run(args.docs)
