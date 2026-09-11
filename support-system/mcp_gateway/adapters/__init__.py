from typing import Protocol, Dict, Any
from ..contract import (
    OrderStatusResult,
    RefundResult,
    CancelResult,
    AddressUpdateResult,
    BillingResult
)

class AdapterProtocol(Protocol):
    """
    The shared interface that every backend adapter MUST implement.
    The MCP server delegates to these methods.
    """
    def get_order_status(self, order_id: str) -> OrderStatusResult: ...
    def issue_refund(self, order_id: str, amount: float, reason: str) -> RefundResult: ...
    def cancel_order(self, order_id: str, reason: str) -> CancelResult: ...
    def update_shipping_address(self, order_id: str, new_address: Dict[str, Any]) -> AddressUpdateResult: ...
    def get_billing_details(self, customer_id: str) -> BillingResult: ...
