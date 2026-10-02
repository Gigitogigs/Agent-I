from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID

class ConnectorConfigField(BaseModel):
    name: str
    type: str
    required: bool
    secret: bool

class ConnectorCatalogEntry(BaseModel):
    id: str
    display_name: str
    domains: List[str]
    transport: str
    config_fields: List[ConnectorConfigField]
    is_configured: bool
    status: Optional[str] = None
    integration_id: Optional[UUID] = None
