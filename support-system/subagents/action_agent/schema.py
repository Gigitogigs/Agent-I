# subagents/action_agent/schema.py
#
# Input / output schemas for the Account / Order Action Agent.
#
# Responsibility:
#   Defines the Pydantic models that validate data flowing into and out of
#   the action_agent, enforcing a strict contract between the Orchestrator
#   and the action tool layer.
#
# Expected schemas:
#
#   ActionRequest (input from Orchestrator):
#     - action_type : str   — one of the agent's allowed actions
#                             (e.g. "get_order", "issue_refund", "cancel_order")
#     - params      : dict  — action-specific parameters (order_id, amount, etc.)
#     - session_id  : str   — used to generate the idempotency key
#     - turn_id     : str   — combined with session_id for idempotency
#     - risk_level  : str   — pre-computed by the Orchestrator/Guardrail Layer
#                             ("low" | "medium" | "high")
#
#   ActionResult (output back to Orchestrator):
#     - success         : bool
#     - data            : dict | None  — the tool's response payload on success
#     - error           : str | None   — human-readable error message on failure
#     - needs_approval  : bool         — True if the guardrail flagged this action
#                                        and the Orchestrator should trigger HITL
#     - idempotency_key : str          — echoed back so the Orchestrator can log it

from pydantic import BaseModel
from typing import Optional, Dict, Any


class ActionRequest(BaseModel):
    action_type: str
    params: Dict[str, Any]
    session_id: str
    turn_id: str
    risk_level: str = "low"


class ActionResult(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    needs_approval: bool = False
    idempotency_key: str
