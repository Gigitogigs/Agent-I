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
# Typical fields this schema will contain:
#   - messages          : list of conversation turns (HumanMessage / AIMessage)
#   - session_id        : unique identifier for the conversation thread
#   - intent            : classified intent of the current turn
#                         (e.g. "faq", "order_action", "escalation")
#   - pending_approval  : metadata about any in-flight HITL checkpoint
#                         (checkpoint_id, action, risk_level, expires_at)
#   - subagent_results  : structured outputs returned by subagents in this turn
#   - turn_id           : monotonically increasing counter per turn, used to
#                         generate idempotency keys for mutating tool calls
#
# Access:
#   The Orchestrator is the SOLE WRITER to this state. Subagents are stateless
#   and never mutate it directly; they receive a context slice and return a result.

from typing import Annotated, Literal, Any, Optional, TypedDict
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

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
    query: str
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    customer_context: dict
    
    # Orchestration specific state
    intents: Optional[list[str]]
    urgency: Optional[str]
    requires_human: Optional[bool]
    context_slice: list[str]
    subagent_results: Annotated[dict, merge_results]
    pending_approval: dict
    requesting_agent: Optional[str]
