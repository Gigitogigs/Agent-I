# observability/tracing.py
#
# Langfuse tracing integration for the multi-agent support system.
#
# Responsibility:
#   Provides helper functions and context managers to emit structured traces
#   and spans to the self-hosted Langfuse instance. Every conversation turn
#   produces one Langfuse trace; every node within that turn (classification,
#   each subagent call, each tool call, guardrail check) produces a nested span.
#
# Why Langfuse (self-hosted):
#   Chosen over LangSmith to avoid an external service dependency and recurring
#   cost. Langfuse runs as a container alongside the rest of the system
#   (see docker-compose.yml) and uses the same Postgres instance.
#
# What gets traced:
#   - Turn-level trace: session_id, turn_id, intent, end-to-end latency,
#                       total token usage, total cost, final outcome
#   - Node spans:       node name, inputs, outputs (PII-redacted before export),
#                       model used, duration, token counts
#   - Tool call spans:  tool name, params (sanitised), result, latency
#   - Guardrail spans:  verdict (pass/block/flag), reason, risk_level
#   - HITL spans:       checkpoint_id, time-to-decision, operator_id (hashed)
#
# PII handling:
#   All inputs/outputs are PII-redacted by the Guardrail Layer BEFORE being
#   passed to this module for export. Tracing data must never contain raw
#   customer PII.
#
# Emission pattern:
#   Asynchronous, fire-and-forget. A Langfuse export failure must NEVER block
#   or error a live chat turn. Traces are batched and retried internally by
#   the Langfuse SDK.
#
# Metrics surfaced via Langfuse:
#   Request rate, error rate, p50/p95/p99 latency per node, model fallback
#   trigger count, retrieval hit-rate, HITL pending count, SLA breach count,
#   token usage and cost per agent per day.
