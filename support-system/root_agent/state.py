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

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    session_id: str
    thread_id: str
    user_id: str
    customer_context: dict
    risk_level: Optional[Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]]

    # Kept for frontend consumption — populated from ToolMessage results after each tool call
    subagent_results: dict

    # Set when a HITL interrupt has been triggered
    pending_approval: dict

    # The agent that produced the result that triggered a guardrail escalation
    requesting_agent: Optional[str]
