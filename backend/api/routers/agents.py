from typing import Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_db, require_min_role
from backend.api.schemas.agent import AgentConfigOut, AgentConfigUpdate, ApiKeyUpdate, ApiKeyResponse
from backend.services.agent_service import get_agent_config, update_agent_config, update_api_key

router = APIRouter(prefix="/workspaces/{workspace_id}/agents", tags=["agents"])

@router.get("", response_model=AgentConfigOut)
async def get_agents(
    workspace_id: UUID,
    db: AsyncSession = Depends(get_db),
    _membership = Depends(require_min_role("read-only"))
):
    return await get_agent_config(db, workspace_id)

@router.patch("/{agent_type}", response_model=AgentConfigOut)
async def update_agent(
    workspace_id: UUID,
    agent_type: str,
    update_data: AgentConfigUpdate,
    db: AsyncSession = Depends(get_db),
    _membership = Depends(require_min_role("admin"))
):
    return await update_agent_config(db, workspace_id, agent_type, update_data)

@router.put("/{agent_type}/api-key", response_model=ApiKeyResponse)
async def update_agent_api_key(
    workspace_id: UUID,
    agent_type: str,
    api_key_data: ApiKeyUpdate,
    db: AsyncSession = Depends(get_db),
    _membership = Depends(require_min_role("admin"))
):
    hint = await update_api_key(db, workspace_id, agent_type, api_key_data.apiKey, api_key_data.provider)
    return ApiKeyResponse(apiKeyHint=hint)
