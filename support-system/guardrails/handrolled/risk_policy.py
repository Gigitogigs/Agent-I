from typing import Literal
import os
import sys

# Ensure mcp_gateway can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from mcp_gateway.risk_tiers import TOOL_RISK_TIERS

def get_risk_tier(tool_name: str) -> Literal["low", "medium", "high", "critical"]:
    """
    Returns the authoritative risk tier for a given tool name.
    If the tool is unknown, defaults to 'high' for safety.
    """
    return TOOL_RISK_TIERS.get(tool_name, "high")  # type: ignore
