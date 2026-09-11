from pydantic import BaseModel
from typing import Dict, Any, Optional

class ActionRequest(BaseModel):
    action_type: str
    params: Dict[str, Any]
    session_id: str
    turn_id: str  # Note: Keeping as string because graph.py calls it as string
    risk_level: str = "low"

class ActionResult(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    needs_approval: bool = False
    idempotency_key: str
