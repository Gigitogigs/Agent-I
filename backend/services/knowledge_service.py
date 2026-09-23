import os
import uuid
import traceback
from typing import Dict, Any, List
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from langchain_core.documents import Document as LangchainDocument
from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.db.session import AsyncSessionLocal
from backend.db.models.knowledge import Document, DocumentChunk
from support_system.rag import pgvector_client

# Loaders
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.document_loaders import Docx2txtLoader
from langchain_community.document_loaders import CSVLoader
from langchain_community.document_loaders import UnstructuredExcelLoader
from langchain_community.document_loaders import TextLoader

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "512"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "64"))

splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
)

def get_loader(file_path: str, file_type: str):
    """
    Returns the appropriate LangChain document loader based on the file extension/type.
    """
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == ".pdf":
        return PyPDFLoader(file_path)
    elif ext in [".doc", ".docx"]:
        return Docx2txtLoader(file_path)
    elif ext == ".csv":
        return CSVLoader(file_path)
    elif ext in [".xls", ".xlsx"]:
        return UnstructuredExcelLoader(file_path)
    else:
        # Fallback to TextLoader for .md, .txt
        return TextLoader(file_path)

async def process_document_task(ctx: Dict[Any, Any], document_id: uuid.UUID) -> None:
    """
    ARQ Background Task to process a document.
    1. Loads the document from the DB.
    2. Uses Langchain Loaders to extract text based on file type.
    3. Splits text into chunks.
    4. Upserts to PGVector.
    5. Saves DocumentChunks to DB.
    6. Updates Document status to 'ready'.
    """
    async with AsyncSessionLocal() as db:
        # Fetch document
        stmt = select(Document).where(Document.id == document_id)
        result = await db.execute(stmt)
        doc = result.scalar_one_or_none()
        
        if not doc:
            print(f"Document {document_id} not found.")
            return
            
        try:
            # 1. Load text
            loader = get_loader(doc.file_path, doc.file_type)
            raw_docs = loader.load()
            
            # 2. Split text
            chunks = splitter.split_documents(raw_docs)
            
            # 3. Add metadata (workspace_id is crucial for multi-tenant isolation)
            for c in chunks:
                c.metadata["document_id"] = str(doc.id)
                c.metadata["workspace_id"] = str(doc.workspace_id)
                
            # 4. Upsert to PGVector
            # This returns a list of UUID strings corresponding to the vectors
            vector_ids = pgvector_client.upsert_chunks(chunks)
            
            # 5. Save DocumentChunks to relational DB for auditing
            db_chunks = []
            for idx, (chunk, vector_id) in enumerate(zip(chunks, vector_ids)):
                # Calculate simple token count approx
                token_count = len(chunk.page_content.split()) 
                
                db_chunk = DocumentChunk(
                    document_id=doc.id,
                    workspace_id=doc.workspace_id,
                    chunk_index=idx,
                    content=chunk.page_content,
                    token_count=token_count,
                    langchain_embedding_id=uuid.UUID(vector_id)
                )
                db_chunks.append(db_chunk)
                
            db.add_all(db_chunks)
            
            # 6. Mark Document as ready
            doc.status = "ready"
            doc.chunk_count = len(chunks)
            await db.commit()
            print(f"Successfully processed Document {document_id} into {len(chunks)} chunks.")
            
        except Exception as e:
            # Mark as failed
            doc.status = "failed"
            doc.error_message = str(e)
            await db.commit()
            traceback.print_exc()
            raise # re-raise so ARQ knows it failed and can retry
