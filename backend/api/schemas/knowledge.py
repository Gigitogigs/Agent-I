from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field

class KnowledgeDocumentOut(BaseModel):
    id: UUID
    filename: str
    status: str
    tags: Optional[Dict[str, str]] = Field(default_factory=dict)
    sizeBytes: int = Field(alias="file_size_bytes")
    chunkCount: Optional[int] = Field(alias="chunk_count", default=0)
    uploadedAt: datetime = Field(alias="created_at")
    errorMessage: Optional[str] = Field(alias="error_message", default=None)

    model_config = {
        "populate_by_name": True,
        "from_attributes": True
    }

class UploadResponse(BaseModel):
    id: UUID
    filename: str
    status: str

class TestRetrievalRequest(BaseModel):
    query: str

class RetrievedChunkOut(BaseModel):
    source: str
    chunk: str
    score: float

class TestRetrievalResponse(BaseModel):
    results: List[RetrievedChunkOut]
