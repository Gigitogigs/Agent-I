from uuid import UUID
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from backend.db.models.agent_config import WorkspaceAgentConfig, WorkspaceProviderKey
from backend.api.schemas.agent import AgentConfigOut, AgentDetail, AgentConfigUpdate
from backend.core.security import encrypt_secret

async def get_agent_config(db: AsyncSession, workspace_id: UUID) -> AgentConfigOut:
    config = await db.scalar(select(WorkspaceAgentConfig).where(WorkspaceAgentConfig.workspace_id == workspace_id))
    
    if not config:
        # Create default config if it doesn't exist
        config = WorkspaceAgentConfig(workspace_id=workspace_id, active_provider="anthropic")
        db.add(config)
        await db.commit()
        await db.refresh(config)

    # Fetch provider key hint
    key_hint = None
    provider_key = await db.scalar(
        select(WorkspaceProviderKey)
        .where(WorkspaceProviderKey.workspace_id == workspace_id)
        .where(WorkspaceProviderKey.provider == config.active_provider)
    )
    if provider_key:
        key_hint = provider_key.key_hint

    def build_agent_detail(agent_id: str) -> AgentDetail:
        return AgentDetail(
            id=agent_id,
            provider=config.active_provider,
            model=config.custom_models.get(agent_id) if config.custom_models else config.global_model,
            systemPrompt=config.custom_prompts.get(agent_id) if config.custom_prompts else config.global_system_prompt,
            tools=config.custom_tools.get(agent_id) if config.custom_tools else None,
            guardrails=config.custom_guardrails.get(agent_id) if config.custom_guardrails else None,
            hitlBreakpoints=config.custom_hitl_breakpoints.get(agent_id) if config.custom_hitl_breakpoints else None,
            apiKeyHint=key_hint
        )

    return AgentConfigOut(
        global_=AgentDetail(
            id="global",
            provider=config.active_provider,
            model=config.global_model,
            systemPrompt=config.global_system_prompt,
            apiKeyHint=key_hint
        ),
        orchestrator=build_agent_detail("orchestrator"),
        retrieval=build_agent_detail("retrieval"),
        action=build_agent_detail("action"),
        escalation=build_agent_detail("escalation")
    )

async def update_agent_config(db: AsyncSession, workspace_id: UUID, agent_type: str, update_data: AgentConfigUpdate) -> AgentConfigOut:
    # Use get_agent_config to guarantee it exists/is seeded
    await get_agent_config(db, workspace_id)
    config = await db.scalar(select(WorkspaceAgentConfig).where(WorkspaceAgentConfig.workspace_id == workspace_id))
        
    def _update_jsonb(col_name: str, key: str, val: Any):
        col = getattr(config, col_name) or {}
        if val is not None:
            col[key] = val
            # SQLAlchemy JSON mutations might need to be explicitly flagged
            # We assign a new dict to ensure it triggers update
            setattr(config, col_name, dict(col))

    if agent_type == "global":
        if update_data.model is not None:
            config.global_model = update_data.model
        if update_data.systemPrompt is not None:
            config.global_system_prompt = update_data.systemPrompt
    else:
        _update_jsonb("custom_models", agent_type, update_data.model)
        _update_jsonb("custom_prompts", agent_type, update_data.systemPrompt)
        
        # New columns for tools, guardrails, HITL
        if update_data.tools is not None:
            _update_jsonb("custom_tools", agent_type, update_data.tools)
        if update_data.guardrails is not None:
            _update_jsonb("custom_guardrails", agent_type, update_data.guardrails)
        if update_data.hitlBreakpoints is not None:
            # We convert Pydantic objects to dicts before storing in JSONB
            hitl_dicts = [b.dict() for b in update_data.hitlBreakpoints]
            _update_jsonb("custom_hitl_breakpoints", agent_type, hitl_dicts)

    await db.commit()
    return await get_agent_config(db, workspace_id)

