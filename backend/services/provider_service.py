from typing import List
from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.messages import HumanMessage

from backend.core.providers import PROVIDER_CATALOG
from backend.core.security import encrypt_secret, decrypt_secret
from backend.db.models.agent_config import WorkspaceProviderKey, WorkspaceAgentConfig

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from support_system.harness.model_factory import build_model

async def list_providers(db: AsyncSession, workspace_id: UUID) -> List[dict]:
    """Return all providers from the catalog merged with the workspace's configured keys."""
    # Fetch configured keys
    stmt = select(WorkspaceProviderKey).where(WorkspaceProviderKey.workspace_id == workspace_id)
    result = await db.execute(stmt)
    configured_keys = {k.provider: k for k in result.scalars().all()}
    
    out = []
    for provider_id, info in PROVIDER_CATALOG.items():
        db_key = configured_keys.get(provider_id)
        
        # Ollama and others that don't require keys are always considered "verified"
        if not info["requires_key"]:
            is_verified = True
            hint = None
        else:
            is_verified = db_key.is_verified if db_key else False
            hint = db_key.key_hint if db_key else None
            
        out.append({
            "id": provider_id,
            "name": info["name"],
            "isVerified": is_verified,
            "apiKeyHint": hint,
            "models": info["models"]
        })
    return out

async def update_api_key(db: AsyncSession, workspace_id: UUID, provider_id: str, api_key: str) -> str:
    """Upsert an encrypted API key for a provider."""
    if provider_id not in PROVIDER_CATALOG:
        raise HTTPException(status_code=404, detail="Provider not supported.")
        
    if not PROVIDER_CATALOG[provider_id]["requires_key"]:
        raise HTTPException(status_code=400, detail="This provider does not require an API key.")
        
    hint = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "***"
    encrypted = encrypt_secret(api_key)
    
    # Check if exists
    stmt = select(WorkspaceProviderKey).where(
        WorkspaceProviderKey.workspace_id == workspace_id,
        WorkspaceProviderKey.provider == provider_id
    )
    result = await db.execute(stmt)
    db_key = result.scalar_one_or_none()
    
    if db_key:
        db_key.encrypted_api_key = encrypted
        db_key.key_hint = hint
        db_key.is_verified = False
    else:
        db_key = WorkspaceProviderKey(
            workspace_id=workspace_id,
            provider=provider_id,
            encrypted_api_key=encrypted,
            key_hint=hint,
            is_verified=False
        )
        db.add(db_key)
        
    # Update active provider in WorkspaceAgentConfig to point to the newly updated key
    config = await db.scalar(select(WorkspaceAgentConfig).where(WorkspaceAgentConfig.workspace_id == workspace_id))
    if not config:
        config = WorkspaceAgentConfig(workspace_id=workspace_id, active_provider=provider_id)
        db.add(config)
    else:
        config.active_provider = provider_id
        
    await db.commit()
    return hint

async def delete_api_key(db: AsyncSession, workspace_id: UUID, provider_id: str):
    """Delete an API key. Blocked if it's the active provider."""
    # Check if active
    config = await db.scalar(select(WorkspaceAgentConfig).where(WorkspaceAgentConfig.workspace_id == workspace_id))
    if config and config.active_provider == provider_id:
        raise HTTPException(
            status_code=409, 
            detail=f"Cannot delete the key for '{provider_id}' because it is the currently active provider."
        )
        
    stmt = select(WorkspaceProviderKey).where(
        WorkspaceProviderKey.workspace_id == workspace_id,
        WorkspaceProviderKey.provider == provider_id
    )
    result = await db.execute(stmt)
    db_key = result.scalar_one_or_none()
    
    if db_key:
        await db.delete(db_key)
        await db.commit()

async def verify_provider(db: AsyncSession, workspace_id: UUID, provider_id: str):
    """Make a test LLM call to verify the configured key."""
    if provider_id not in PROVIDER_CATALOG:
        raise HTTPException(status_code=404, detail="Provider not supported.")
        
    if not PROVIDER_CATALOG[provider_id]["requires_key"]:
        return # nothing to verify
        
    stmt = select(WorkspaceProviderKey).where(
        WorkspaceProviderKey.workspace_id == workspace_id,
        WorkspaceProviderKey.provider == provider_id
    )
    result = await db.execute(stmt)
    db_key = result.scalar_one_or_none()
    
    if not db_key:
        raise HTTPException(status_code=400, detail="No API key configured for this provider.")
        
    try:
        raw_key = decrypt_secret(db_key.encrypted_api_key)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to decrypt API key.")
        
    # Use the first model in the catalog for testing
    test_model = PROVIDER_CATALOG[provider_id]["models"][0]
    
    try:
        model = build_model({
            "provider": provider_id,
            "model": test_model,
            "api_key": raw_key,
            "max_tokens": 5
        })
        # Make a tiny lightweight call
        await model.ainvoke([HumanMessage(content="Say hello.")])
        
        db_key.is_verified = True
        await db.commit()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Verification failed: {str(e)}")
