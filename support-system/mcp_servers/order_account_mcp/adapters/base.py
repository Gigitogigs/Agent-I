from typing import Protocol, Dict, Any, runtime_checkable
from .schemas import (
    OrderStatusResult,
    RefundResult,
    CancelResult,
    AddressUpdateResult,
    BillingResult,
    OrderHistoryResult,
    AccountDetailsResult
)

@runtime_checkable
class AdapterProtocol(Protocol):
    """
    Structural interface that every order/account backend adapter must satisfy.

    Both ``ShopifyAdapter`` and ``InHouseAdapter`` implement this protocol so that
    ``server.py`` can delegate to either backend transparently. The MCP server
    selects the concrete adapter at startup via the ``ADAPTER_TYPE`` environment
    variable and calls these methods directly.

    All mutating operations (``issue_refund``, ``cancel_order``,
    ``update_shipping_address``) require an ``idempotency_key`` so that callers
    can safely retry on network failure without causing duplicate side-effects.
    """
    def get_order_status(self, order_id: str) -> OrderStatusResult:
        """Return the current fulfilment status of a single order.

        Args:
            order_id: Platform-specific unique order identifier.

        Returns:
            An :class:`OrderStatusResult` with the order's current status string.
        """
        ...

    def get_order_history(self, customer_id: str) -> OrderHistoryResult:
        """Return the full order history for a customer.

        Args:
            customer_id: Platform-specific unique customer identifier.

        Returns:
            An :class:`OrderHistoryResult` containing a list of past order records.
        """
        ...

    def get_account_details(self, customer_id: str) -> AccountDetailsResult:
        """Return profile and account metadata for a customer.

        Args:
            customer_id: Platform-specific unique customer identifier.

        Returns:
            An :class:`AccountDetailsResult` with the customer's account fields.
        """
        ...

    def get_billing_details(self, customer_id: str) -> BillingResult:
        """Return billing and payment information for a customer.

        Args:
            customer_id: Platform-specific unique customer identifier.

        Returns:
            A :class:`BillingResult` containing billing gateway and payment details.
        """
        ...

    # Mutating actions MUST accept an idempotency_key
    def issue_refund(self, order_id: str, amount: float, reason: str, idempotency_key: str) -> RefundResult:
        """Initiate a refund for a given order.

        Args:
            order_id: Platform-specific unique order identifier.
            amount: The monetary amount to refund (in the store's default currency).
            reason: Human-readable reason for the refund (e.g. ``"damaged_item"``).
            idempotency_key: A unique caller-generated key that prevents duplicate
                refunds if the request is retried after a network failure.

        Returns:
            A :class:`RefundResult` with the assigned refund ID and confirmed amount.
        """
        ...

    def cancel_order(self, order_id: str, reason: str, idempotency_key: str) -> CancelResult:
        """Cancel an order that has not yet been fulfilled.

        Args:
            order_id: Platform-specific unique order identifier.
            reason: Human-readable reason for the cancellation.
            idempotency_key: A unique caller-generated key to prevent duplicate
                cancellations on retry.

        Returns:
            A :class:`CancelResult` indicating whether the cancellation succeeded.
        """
        ...

    def update_shipping_address(self, order_id: str, new_address: Dict[str, Any], idempotency_key: str) -> AddressUpdateResult:
        """Update the shipping address on an existing order.

        Args:
            order_id: Platform-specific unique order identifier.
            new_address: Dict containing the new address fields (e.g. ``street``,
                ``city``, ``country``, ``postal_code``).
            idempotency_key: A unique caller-generated key to prevent duplicate
                address updates on retry.

        Returns:
            An :class:`AddressUpdateResult` indicating whether the update succeeded.
        """
        ...
