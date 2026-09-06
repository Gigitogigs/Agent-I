# approvals/models.py
#
# Data models for the HITL (Human-in-the-Loop) approval system.
#
# Responsibility:
#   Defines the Pydantic models (and/or SQLAlchemy ORM models) that represent
#   HITL approval records in the system. These models are the source of truth
#   for the approval lifecycle state machine.
#
# State machine:
#   pending → approved  (operator approved within SLA)
#   pending → rejected  (operator rejected within SLA)
#   pending → expired   (SLA timer elapsed without a decision;
#                        default policy: auto-escalate)
#   pending → cancelled (action was superseded or the session was terminated)
#
# Key design constraints from the architecture:
#   - Cross-agent isolation is enforced at the DATABASE layer via Postgres
#     Row-Level Security (RLS) scoped by session_id / tenant_id. The application
#     layer must NOT be trusted to enforce this isolation on its own.
#   - Every approval record is also written to the append-only audit_log table
#     independently of Langfuse traces (audit log has longer retention and is
#     compliance-grade; traces are for debugging/performance).
#   - Operator permissions are RBAC-controlled: different operator roles may
#     approve different breakpoint types (e.g. a billing team member approves
#     refunds, a senior agent approves account closures).
#
# Expected fields:
#   - id              : UUID         — primary key
#   - session_id      : str          — conversation thread this belongs to
#   - turn_id         : int          — the turn that triggered this approval
#   - action          : dict         — serialised proposed action payload
#   - risk_level      : str          — "medium" | "high"
#   - risk_reason     : str          — explanation from the Guardrail Layer
#   - status          : str          — current state machine status (see above)
#   - created_at      : datetime
#   - expires_at      : datetime     — SLA deadline
#   - resolved_at     : datetime | None
#   - resolved_by     : str | None   — operator ID who made the decision
#   - operator_note   : str | None
