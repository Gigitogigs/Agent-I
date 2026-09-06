# subagents/action_agent/graph.py
#
# LangGraph graph definition for the Account / Order Action Agent.
#
# Responsibility:
#   Executes account and order operations against external systems on behalf
#   of the customer. This agent is invoked as a "tool" by the Orchestrator —
#   it receives a structured action request, runs it through the Tool Layer,
#   and returns a structured result.
#
# Stateless by design:
#   This agent has NO memory of previous turns. It receives exactly the context
#   the Orchestrator provides for this single invocation, does its job, and
#   returns. This keeps failure domains small and makes the agent independently
#   testable and swappable.
#
# Node layout (high-level):
#   1. validate_params  — schema-validate incoming action params; reject malformed
#                         requests before they reach external systems
#   2. guardrail_check  — assess risk level of the proposed action:
#                           LOW  (read-only, e.g. get_order) → proceed autonomously
#                           MEDIUM/HIGH (mutating, e.g. issue_refund) → route to
#                           guardrail layer; HIGH actions trigger HITL interrupt
#   3. execute_tool     — call the appropriate Tool Layer adapter with an
#                         idempotency key (session_id + turn_id + action_type) to
#                         prevent double-execution on retries
#   4. handle_result    — map the external system response to a structured
#                         AgentResult and surface any errors with retry logic
#                         (exponential backoff, bounded retries)
#
# Parallelism:
#   Read-only calls (e.g. get_order) may be fanned out in parallel by the
#   Orchestrator. Mutating calls are always serialised per session.
#
# Tool allowlist:
#   get_order, issue_refund, update_shipping_address, cancel_order, get_billing
#   Each tool is tagged with a risk level; the Tool Layer rejects any call to
#   a tool not on this agent's allowlist, independent of what the LLM decides.
