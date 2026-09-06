from subagents.escalation_agent.graph import invoke_escalation_agent
from subagents.retrieval_agent.graph import invoke_retrieval_agent

TOOL_REGISTRY={
    "retrieval_agent": invoke_retrieval_agent,
    "escalation_agent": invoke_escalation_agent
}

def resolve_tools(tool_names: list) -> list:
    """
    Converts a list of tool names strings (from YAML) to actual tool objects.
    """
    return [TOOL_REGISTRY[name] for name in tool_names if name in TOOL_REGISTRY]