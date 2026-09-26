import os
import shutil
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from backend.api.dependencies import get_db, require_min_role
from backend.db.models.knowledge import Document
from backend.api.schemas.knowledge import KnowledgeDocumentOut, TestRetrievalRequest, TestRetrievalResponse, UploadResponse, RetrievedChunkOut
from support_system.rag import pgvector_client

from arq import create_pool
from arq.connections import RedisSettings
from backend.core.config import settings

router = APIRouter(prefix="/workspaces", tags=["knowledge"])

ALLOWED_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".txt": "text/plain",
    ".md": "text/markdown"
}

# Create a dedicated uploads folder
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

from backend.core.arq import get_arq_redis

@router.get(
    "/{workspace_id}/knowledge-base",
    response_model=list[KnowledgeDocumentOut],
    dependencies=[Depends(require_min_role("read-only"))]
)
async def list_documents(
    workspace_id: UUID,
    search: str = None,
    status: str = None,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Document).where(Document.workspace_id == workspace_id)
    if status:
        stmt = stmt.where(Document.status == status)
    if search:
        stmt = stmt.where(Document.filename.ilike(f"%{search}%"))
        
    stmt = stmt.order_by(desc(Document.created_at))
    result = await db.execute(stmt)
    docs = result.scalars().all()
    return docs

@router.post(
    "/{workspace_id}/knowledge-base/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_202_ACCEPTED
)
async def upload_document(
    workspace_id: UUID,
    # Need to simulate extracting the user ID from token since we use require_min_role.
    # In a real app we'd inject the current user. For now we mock it or allow nullable.
    # We'll fetch the workspace to get an owner ID, or just pass a dummy if allowed.
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    # In this test environment, we don't have access to the actual token user here unless we use a dependency.
    # For now, we'll just set uploaded_by_user_id to the workspace's first member
    from backend.db.models.workspace_member import WorkspaceMember
    mem_result = await db.execute(select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id).limit(1))
    member = mem_result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Workspace has no members")
    user_id = member.user_id

    # Validate file extension
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file extension: {ext}")
        
    # Save file to disk securely
    import uuid
    safe_filename = f"{workspace_id}_{uuid.uuid4()}{ext}"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    file_size = os.path.getsize(file_path)
    
    # Create DB record
    doc = Document(
        workspace_id=workspace_id,
        uploaded_by_user_id=user_id,
        filename=file.filename,
        file_path=file_path,
        file_type=file.content_type or ALLOWED_EXTENSIONS[ext],
        file_size_bytes=file_size,
        status="processing"
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    
    # Enqueue ARQ task
    redis = await get_arq_redis()
    await redis.enqueue_job("process_document_task", doc.id)
    
    return UploadResponse(id=doc.id, filename=doc.filename, status=doc.status)

@router.delete(
    "/{workspace_id}/knowledge-base/{doc_id}",
    status_code=status.HTTP_200_OK
)
async def delete_document(
    workspace_id: UUID,
    doc_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    doc = await db.get(Document, doc_id)
    if not doc or doc.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Document not found")
        
    # Delete from vector store
    pgvector_client.delete_document(str(doc.id))
    
    # Delete from relational store
    await db.delete(doc)
    await db.commit()
    
    # Delete file from disk
    if os.path.exists(doc.file_path):
        os.remove(doc.file_path)
        
    return {"status": "deleted"}

@router.post(
    "/{workspace_id}/knowledge-base/{doc_id}/retry",
    status_code=status.HTTP_202_ACCEPTED
)
async def retry_document(
    workspace_id: UUID,
    doc_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    doc = await db.get(Document, doc_id)
    if not doc or doc.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Document not found")
        
    doc.status = "processing"
    doc.error_message = None
    await db.commit()
    
    redis = await get_arq_redis()
    await redis.enqueue_job("process_document_task", doc.id)
    
    return {"status": "retrying"}

@router.post(
    "/{workspace_id}/knowledge-base/test-retrieval",
    response_model=TestRetrievalResponse,
    dependencies=[Depends(require_min_role("read-only"))]
)
async def test_retrieval(
    workspace_id: UUID,
    request: TestRetrievalRequest
):
    # We restrict search to ONLY chunks belonging to this workspace
    results = pgvector_client.similarity_search(
        query=request.query,
        top_k=5,
        filter={"workspace_id": str(workspace_id)}
    )
    
    response_items = []
    for r in results:
        # Reconstruct the response
        source = r.metadata.get("source", "unknown")
        # Find document name if source is missing or is just an ID. 
        # Actually our ingestion sets document_id, we can look up the filename.
        # But for test, returning the document_id as source is fine.
        response_items.append(RetrievedChunkOut(
            source=r.metadata.get("document_id", source),
            chunk=r.page_content,
            score=0.0 # Langchain's base similarity_search doesn't return scores easily. We'd use similarity_search_with_score if we need it.
        ))
        
    return TestRetrievalResponse(results=response_items)
