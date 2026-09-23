from typing import Dict, Any

def validate_action(action_payload: Dict[str, Any]) -> str:
    """
    Validates a proposed action from a subagent.
    Returns the risk level: "LOW", "MEDIUM", "HIGH", "CRITICAL".
    
    For now, this is a mock implementation that flags any refund over 100 as HIGH risk.
    """
    if "refund_amount" in action_payload:
        if action_payload["refund_amount"] > 100:
            return "HIGH"
        return "MEDIUM"
    
    if "cancel_order" in action_payload:
        return "HIGH"
        
    return "LOW"
