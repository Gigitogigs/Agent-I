import asyncio
import json
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from langchain_core.messages import HumanMessage

from backend.db.models.chat import Conversation, ConversationTurn
from backend.db.models.agent_config import WorkspaceAgentConfig, WorkspaceProviderKey
from support_system.root_agent.graph import root_agent

async def build_agent_config(db: AsyncSession, workspace_id: UUID) -> dict:
    """
    Fetches the workspace's agent config and API key from the DB and 
    formats it into the nested structure expected by the LangGraph subagents.
    """
    config_result = await db.execute(
        select(WorkspaceAgentConfig).where(WorkspaceAgentConfig.workspace_id == workspace_id)
    )
    workspace_config = config_result.scalar_one_or_none()
    
    if not workspace_config:
        # Fallback to empty config, model_factory will fail if missing required keys
        return {}
        
    provider = workspace_config.active_provider
    api_key = None
    
    key_result = await db.execute(
        select(WorkspaceProviderKey)
        .where(WorkspaceProviderKey.workspace_id == workspace_id)
        .where(WorkspaceProviderKey.provider == provider)
    )
    workspace_key = key_result.scalar_one_or_none()
    if workspace_key:
        api_key = workspace_key.encrypted_api_key # TODO: add decryption here if needed

    # Build the dynamic config
    agent_config = {
        "orchestrator": {
            "provider": provider,
            "model": workspace_config.global_model,
            "temperature": workspace_config.global_temperature,
            "system_prompt": workspace_config.global_system_prompt,
            "api_key": api_key,
            "tools": ["retrieval_agent", "action_agent", "escalation_agent"]
        },
        "subagents": {
            "retrieval_agent": {
                "provider": provider,
                "model": workspace_config.global_model,
                "temperature": workspace_config.global_temperature,
                "api_key": api_key,
            },
            "action_agent": {
                "provider": provider,
                "model": workspace_config.global_model,
                "temperature": workspace_config.global_temperature,
                "api_key": api_key,
            },
            "escalation_agent": {
                 # Escalation agent doesn't actually use an LLM right now, but we'll populate just in case
                "provider": provider,
                "model": workspace_config.global_model,
                "temperature": workspace_config.global_temperature,
                "api_key": api_key,
            }
        }
    }
    
    # Override with custom_models if the mode allows it
    if workspace_config.mode == "custom":
        if workspace_config.custom_models:
             for agent, model_name in workspace_config.custom_models.items():
                 if agent == "orchestrator":
                     agent_config["orchestrator"]["model"] = model_name
                 elif agent in agent_config["subagents"]:
                     agent_config["subagents"][agent]["model"] = model_name
    
    return agent_config


async def process_chat_turn(
    db: AsyncSession, 
    workspace_id: UUID, 
    conversation_id: UUID, 
    message: str
) -> dict:
    """
    Processes a customer chat turn asynchronously by delegating to LangGraph 
    in a separate threadpool to avoid blocking the asyncio event loop.
    """
    
    # 1. Save user turn
    # Determine the turn_index by counting existing turns
    turn_count_res = await db.execute(
        select(ConversationTurn).where(ConversationTurn.conversation_id == conversation_id)
    )
    turn_index = len(turn_count_res.scalars().all())
    
    user_turn = ConversationTurn(
        conversation_id=conversation_id,
        workspace_id=workspace_id,
        turn_index=turn_index,
        role="customer",
        content=message
    )
    db.add(user_turn)
    await db.commit()
    
    # 2. Build agent config
    agent_config_dict = await build_agent_config(db, workspace_id)
    
    # 3. Invoke LangGraph synchronously in a thread
    def run_graph_sync():
        state = {
            "messages": [HumanMessage(content=message)],
            "session_id": str(conversation_id)
        }
        config = {
            "configurable": {
                "thread_id": str(conversation_id),
                "agent_config": agent_config_dict
            }
        }
        return root_agent.invoke(state, config=config)

    graph_result = await asyncio.to_thread(run_graph_sync)
    
    # 4. Extract final AI response
    final_message = graph_result["messages"][-1].content
    subagent_results = graph_result.get("subagent_results", {})
    
    # 5. Save AI turn
    ai_turn = ConversationTurn(
        conversation_id=conversation_id,
        workspace_id=workspace_id,
        turn_index=turn_index + 1,
        role="agent",
        agent_id="orchestrator",
        content=final_message
        # We could also parse out token usage and latency here if needed
    )
    db.add(ai_turn)
    await db.commit()
    await db.refresh(ai_turn)
    
    return {
        "response": final_message,
        "turn_id": ai_turn.id,
        "subagent_results": subagent_results
    }
