# subagents/escalation_agent/schema.py
#
# Input / output schemas for the Escalation / HITL Agent.
#
# Responsibility:
#   Defines the Pydantic models that validate data flowing into and out of
#   the escalation_agent, enforcing a strict contract between the Orchestrator
#   and the HITL lifecycle.
#
# Expected schemas:
#
#   EscalationRequest (input from Orchestrator / Guardrail Layer):
#     - session_id       : str    — conversation thread this belongs to
#     - ticket_id        : str    — ID of the ticket 
#     - escalation_type  : str    — "hitl_approval" | "human_handoff"
#     - action           : dict   — the proposed action awaiting approval
#                                   (for hitl_approval; None for human_handoff)
#     - risk_level       : str    — "medium" | "high"
#     - risk_reason      : str    — human-readable explanation of why flagged
#     - sla_seconds      : int    — seconds until this checkpoint expires;
#                                   default is configurable per breakpoint type
#
#   EscalationResult (output back to Orchestrator):
#     - checkpoint_id    : str    — ID of the created Postgres HITL record
#     - status           : str    — "pending" | "approved" | "rejected" |
#                                   "expired" | "cancelled"
#     - operator_note    : str | None  — optional note left by the operator
#     - resolved_at      : datetime | None
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, field_validator


def _make_json_safe(obj: Any) -> Any:
    """
    Recursively converts non-JSON-serializable Python types to JSON-safe equivalents.

    Handles sets and tuples (converted to lists), dicts (values recursed),
    and lists (items recursed). All other types are returned unchanged.

    This is needed because the Orchestrator LLM occasionally generates tool call
    arguments containing set literals (e.g. {"item1", "item2"}) in dict fields,
    which causes a TypeError in langchain_core's AIMessage JSON serialization
    before the tool function even executes.

    Args:
        obj: Any Python value to sanitize.

    Returns:
        A JSON-serializable equivalent of the input.
    """
    if isinstance(obj, (set, tuple)):
        return [_make_json_safe(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_make_json_safe(i) for i in obj]
    return obj


class EscalationRequest(BaseModel):
    session_id: str
    agent_id: str
    action_type: str
    payload: dict
    status: str = "pending"
    risk_level: str
    expires_at: Optional[datetime] = None  # TODO: add a default value later on. Make it so it dynamically set.

    @field_validator("payload", mode="before")
    @classmethod
    def sanitize_payload(cls, v: Any) -> Any:
        """
        Sanitizes the payload dict to ensure all values are JSON serializable.

        The Orchestrator LLM may produce set or tuple literals inside the payload
        (e.g. proposed_action: {action1, action2}). These are not JSON serializable
        and crash langchain_core before the tool executes. This validator converts
        them to lists recursively.

        Args:
            v: The raw payload value passed to the model.

        Returns:
            A JSON-safe dict.
        """
        return _make_json_safe(v) if isinstance(v, dict) else v


class EscalationResults(BaseModel):
    id: str
    session_id: str
    reviewer_role: Optional[str] = None
    resolved_by: Optional[str] = None
    status: str
    resolved_at: Optional[datetime] = None