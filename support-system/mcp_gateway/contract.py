from pydantic import BaseModel
from typing import Optional, Dict, Any

# ==============================================================================
# Canonical Tool Results
# ==============================================================================
# Every tool, regardless of backend, must return one of these shapes.

class BaseToolResult(BaseModel):
    success: bool
    error: Optional[str] = None

class OrderStatusResult(BaseToolResult):
    status: Optional[str] = None

class RefundResult(BaseToolResult):
    refund_id: Optional[str] = None
    amount: Optional[float] = None

class CancelResult(BaseToolResult):
    cancelled: bool = False

class AddressUpdateResult(BaseToolResult):
    updated: bool = False

class BillingResult(BaseToolResult):
    billing_info: Optional[Dict[str, Any]] = None
