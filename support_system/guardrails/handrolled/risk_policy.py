import os
import yaml
from typing import Literal
from datetime import datetime, timedelta, timezone

# Path to the risk_tiers.yaml file in the same directory
TIERS_FILE_PATH = os.path.join(os.path.dirname(__file__), "risk_tiers.yaml")

# Load tiers once at module import
with open(TIERS_FILE_PATH, "r") as f:
    config = yaml.safe_load(f) or {}

TOOL_RISK_TIERS = config.get("tools", {})
SLA_TIERS = config.get("tiers", {})

def get_risk_tier(tool_name: str) -> Literal["low", "medium", "high", "critical"]:
    """
    Returns the authoritative risk tier for a given tool name.
    If the tool is unknown, defaults to 'high' for safety.
    """
    return TOOL_RISK_TIERS.get(tool_name, "high")  # type: ignore

def get_expiration(risk_level: str) -> datetime:
    """
    Calculates the absolute expiration timestamp (expires_at) based on the risk tier's configured SLA.
    """
    tier_config = SLA_TIERS.get(risk_level.lower(), {})
    sla_hours = tier_config.get("sla_hours", 24)  # Default to 24 hours if unspecified
    return datetime.now(timezone.utc) + timedelta(hours=sla_hours)
