from typing import Literal
import os
import yaml

# Path to the risk_tiers.yaml file in the same directory
TIERS_FILE_PATH = os.path.join(os.path.dirname(__file__), "risk_tiers.yaml")

# Load tiers once at module import
with open(TIERS_FILE_PATH, "r") as f:
    TOOL_RISK_TIERS = yaml.safe_load(f) or {}

def get_risk_tier(tool_name: str) -> Literal["low", "medium", "high", "critical"]:
    """
    Returns the authoritative risk tier for a given tool name.
    If the tool is unknown, defaults to 'high' for safety.
    """
    return TOOL_RISK_TIERS.get(tool_name, "high")  # type: ignore
