from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_db, require_min_role
from backend.api.schemas.providers import ProviderInfo, ProviderKeyUpdate, ProviderKeyResponse
from backend.api.schemas.auth import MessageResponse
from backend.services.provider_service import (
    list_providers,
    update_api_key,
    delete_api_key,
    verify_provider
)

router = APIRouter(prefix="/workspaces/{workspace_id}/providers", tags=["providers"])

@router.get("", response_model=List[ProviderInfo], dependencies=[Depends(require_min_role("admin"))])
async def get_providers_endpoint(
    workspace_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """List configured providers and their verification status."""
    return await list_providers(db, workspace_id)

@router.put("/{provider_id}/api-key", response_model=ProviderKeyResponse, dependencies=[Depends(require_min_role("admin"))])
async def update_api_key_endpoint(
    workspace_id: UUID,
    provider_id: str,
    body: ProviderKeyUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Add or update an API key for a provider."""
    hint = await update_api_key(db, workspace_id, provider_id, body.apiKey)
    return ProviderKeyResponse(apiKeyHint=hint)

@router.post("/{provider_id}/verify", response_model=MessageResponse, dependencies=[Depends(require_min_role("admin"))])
async def verify_provider_endpoint(
    workspace_id: UUID,
    provider_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Test the key with a lightweight API call and mark it as verified."""
    await verify_provider(db, workspace_id, provider_id)
    return MessageResponse(message="Provider API key verified successfully.")

@router.delete("/{provider_id}/api-key", response_model=MessageResponse, dependencies=[Depends(require_min_role("admin"))])
async def delete_api_key_endpoint(
    workspace_id: UUID,
    provider_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Remove a provider key."""
    await delete_api_key(db, workspace_id, provider_id)
    return MessageResponse(message="API key deleted successfully.")
