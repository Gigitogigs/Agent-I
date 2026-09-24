from typing import List, Optional
from pydantic import BaseModel

class ProviderInfo(BaseModel):
    id: str
    name: str
    isVerified: bool
    apiKeyHint: Optional[str] = None
    models: List[str]

class ProviderKeyUpdate(BaseModel):
    apiKey: str

class ProviderKeyResponse(BaseModel):
    apiKeyHint: str
