# DEPRECATED — This module is no longer used.
#
# router.py has been superseded by the dynamic tool-calling architecture in
# root_agent/graph.py. The Orchestrator LLM now selects subagent tools
# directly via llm.bind_tools(), replacing the rigid intent classification
# pipeline that previously required this module.
#
# Retained for git history only. Do NOT import from this file.
# -------------------------------------------------------------------


#
# Intent classification and routing logic for the Orchestrator Agent.
#
# Responsibility:
#   Given a user message (and optionally session context), determine which
#   subagent should handle the current turn, then produce the LangGraph edge
#   decision that transitions the graph to the correct node.
#
# This is the single centralised routing choke point in the supervisor
# architecture — all inter-agent routing passes through here; subagents never
# route to each other directly.
#
# Routing targets:
#   - "faq"            → FAQ / RAG Agent (retrieval_agent)
#                        triggered for: policy questions, product info, how-to
#   - "order_action"   → Account / Order Action Agent (action_agent)
#                        triggered for: order status, refunds, cancellations,
#                        shipping address changes, billing
#   - "escalation"     → Escalation / HITL Agent (escalation_agent)
#                        triggered for: out-of-scope, emotional distress,
#                        explicit "speak to a human" requests, or when a prior
#                        subagent returns an unresolvable failure
#
# Classification strategy (to be implemented):
#   A lightweight LLM call (cheaper/faster model configured via model_factory)
#   or a rules-based pre-filter for obvious cases, falling back to LLM for
#   ambiguous ones.
#
# Guardrail hook:
#   Before routing to a mutating subagent (action_agent), the router must
#   confirm the incoming message has passed the input guardrail screen.

from pydantic import BaseModel, Field
from typing import Literal

class RouterDecision(BaseModel):
    intents: list[Literal["faq", "order_action", "escalation"]] = Field(
        description="The classified intents of the user's message. Return multiple if they ask for multiple distinct actions."
    )
    urgency: str = Field(
        description="The urgency of the request (e.g. LOW, HIGH)."
    )
    requires_human: bool = Field(
        description="True if the request is out of scope or the user explicitly asks for a human."
    )

def get_router_decision(llm, message: str) -> RouterDecision:
    """
    Calls the LLM to classify the intent.
    """
    structured_llm = llm.with_structured_output(RouterDecision)
    prompt = (
        "You are an intent classification router. You MUST output a JSON object matching the exact schema.\n"
        "Classify the following customer support message into one or more of three intents: 'faq', 'order_action', or 'escalation'.\n"
        "Also determine urgency (LOW, MEDIUM, HIGH, CRITICAL) and whether it requires a human.\n\n"
        f"Message: {message}"
    )
    
    return structured_llm.invoke(prompt)
