from support_system.subagents.escalation_agent.graph import invoke_escalation_agent
from support_system.subagents.retrieval_agent.graph import invoke_retrieval_agent
from support_system.subagents.action_agent.graph import invoke_action_agent

TOOL_REGISTRY = {
    "retrieval_agent": invoke_retrieval_agent,
    "escalation_agent": invoke_escalation_agent,
    "action_agent": invoke_action_agent,
}

ALL_TOOLS = list(TOOL_REGISTRY.values())


def resolve_tools(tool_names: list) -> list:
    """
    Converts a list of tool name strings (from YAML config) to actual tool objects.

    Args:
        tool_names: List of registered tool name strings (e.g. ["retrieval_agent", "action_agent"]).

    Returns:
        List of callable tool objects corresponding to the given names.
        Names not found in the registry are silently skipped.
    """
    return [TOOL_REGISTRY[name] for name in tool_names if name in TOOL_REGISTRY]