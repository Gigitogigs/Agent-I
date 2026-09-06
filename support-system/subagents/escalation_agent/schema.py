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
from typing import Optional
from pydantic import BaseModel

class EscalationRequest(BaseModel):
    session_id: str
    agent_id: str
    action_type: str
    payload: dict
    status: str = "pending"
    risk_level: str
    expires_at: Optional[datetime] = None #TODO: add a default value later on. Make it so it dyanimcally set.
    

class EscalationResults(BaseModel):
    id: str
    session_id: str
    reviewer_role: Optional[str] = None
    resolved_by: Optional[str] = None
    status: str
    resolved_at: Optional[datetime] = None