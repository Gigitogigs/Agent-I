from pydantic import BaseModel
from typing import Optional, Dict, Any, List

# ==============================================================================
# Canonical Tool Results
# ==============================================================================
# Every tool, regardless of backend, must return one of these shapes.

class BaseToolResult(BaseModel):
    """Base response shape returned by every MCP tool, regardless of backend.

    Attributes:
        success: ``True`` if the operation completed without error, ``False`` otherwise.
        error: Human-readable error message populated only when ``success`` is ``False``.
    """

    success: bool
    error: Optional[str] = None

class OrderStatusResult(BaseToolResult):
    """Result of a ``get_order_status`` call.

    Attributes:
        status: Current fulfilment status of the order
            (e.g. ``"pending"``, ``"processing"``, ``"fulfilled"``, ``"cancelled"``).
    """

    status: Optional[str] = None

class RefundResult(BaseToolResult):
    """Result of an ``issue_refund`` call.

    Attributes:
        refund_id: Unique identifier assigned to the refund transaction by the backend.
        amount: The monetary amount that was actually refunded.
    """

    refund_id: Optional[str] = None
    amount: Optional[float] = None

class CancelResult(BaseToolResult):
    """Result of a ``cancel_order`` call.

    Attributes:
        cancelled: ``True`` if the order was successfully cancelled.
    """

    cancelled: bool = False

class AddressUpdateResult(BaseToolResult):
    """Result of an ``update_shipping_address`` call.

    Attributes:
        updated: ``True`` if the shipping address was successfully updated.
    """

    updated: bool = False

class BillingResult(BaseToolResult):
    """Result of a ``get_billing_details`` call.

    Attributes:
        billing_info: Arbitrary dict of billing fields returned by the backend
            (e.g. payment gateway, card last-four, billing address).
    """

    billing_info: Optional[Dict[str, Any]] = None

class OrderHistoryResult(BaseToolResult):
    """Result of a ``get_order_history`` call.

    Attributes:
        history: List of past order records for the customer, each represented
            as a free-form dict whose exact shape depends on the backend.
    """

    history: Optional[List[Dict[str, Any]]] = None

class AccountDetailsResult(BaseToolResult):
    """Result of a ``get_account_details`` call.

    Attributes:
        details: Arbitrary dict of customer account fields returned by the backend
            (e.g. email, name, created date, loyalty tier).
    """

    details: Optional[Dict[str, Any]] = None
