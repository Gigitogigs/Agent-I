# root_agent/state.py
#
# LangGraph state schema for the Orchestrator (root) Agent.
#
# Responsibility:
#   Defines the TypedDict (or Pydantic model) that represents the full
#   state of one conversation thread inside the LangGraph graph. Every node
#   in the Orchestrator graph reads from and writes to this state object.
#
# Why this matters:
#   LangGraph persists this exact object to Postgres at every node boundary
#   via the checkpointer (see memory/checkpointer.py). This is what makes
#   HITL pause-and-resume possible: if the process crashes or the operator
#   takes hours to approve an action, the graph resumes from the last
#   committed state snapshot, not from in-memory values.
#
# Access:
#   The Orchestrator is the SOLE WRITER to this state. Subagents are stateless
#   and never mutate it directly; they receive a context slice and return a result.

from typing import Annotated, Literal, Any, Optional, TypedDict
from langgraph.graph.message import add_messages

def merge_results(left: dict, right: dict) -> dict:
    if not left:
        return right if right else {}
    if not right:
        return left
    merged = left.copy()
    merged.update(right)
    return merged

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    session_id: str
    thread_id: str
    user_id: str
    customer_context: dict

    risk_level: Optional[Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]]

    # Kept for frontend consumption — populated from ToolMessage results after each tool call
    subagent_results: Annotated[dict, merge_results]

    # Set when a HITL interrupt has been triggered
    pending_approval: dict

    # The agent that produced the result that triggered a guardrail escalation
    requesting_agent: Optional[str]
