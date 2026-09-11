# Mapping of canonical tool names to their risk tier policy.
# This dictates whether an action requires Human-In-The-Loop approval.
# 
# "low" = Proceed autonomously
# "medium" | "high" = Route to Guardrail layer and HITL interrupt

TOOL_RISK_TIERS = {
    "get_order_status": "low",
    "get_billing_details": "low",
    "update_shipping_address": "medium",
    "cancel_order": "high",
    "issue_refund": "high"
}
