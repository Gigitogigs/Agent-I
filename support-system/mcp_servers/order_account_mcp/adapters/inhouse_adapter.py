from typing import Dict, Any
from .schemas import (
    OrderStatusResult,
    RefundResult,
    CancelResult,
    AddressUpdateResult,
    BillingResult,
    OrderHistoryResult,
    AccountDetailsResult
)
from .base import AdapterProtocol

class InHouseAdapter(AdapterProtocol):
    """
    Order/account adapter backed by the client's own internal infrastructure.

    Makes direct REST API calls or database queries to the client's proprietary
    backend instead of a third-party platform. This is the default adapter
    selected when the ``ADAPTER_TYPE`` environment variable is not set to
    ``"shopify"``.

    Args:
        api_base_url: Base URL of the internal REST API
            (e.g. ``"https://api.internal.example.com/v1"``). Must not include a
            trailing slash.
        api_key: Secret key used to authenticate requests to the internal API.
    """

    def __init__(self, api_base_url: str, api_key: str):
        """Store connection details for use in every API call.

        Args:
            api_base_url: Base URL of the internal REST API.
            api_key: API key for authenticating requests.
        """
        self.api_base_url = api_base_url
        self.api_key = api_key

    def get_order_status(self, order_id: str) -> OrderStatusResult:
        """Return the current status of an order from the internal system.

        Args:
            order_id: Internal system order identifier.

        Returns:
            An :class:`OrderStatusResult` with the order's current status string.
        """
        # TODO: Implement internal REST API or DB call
        return OrderStatusResult(success=True, status="processing")

    def get_order_history(self, customer_id: str) -> OrderHistoryResult:
        """Return all past orders for a customer from the internal system.

        Args:
            customer_id: Internal system customer identifier.

        Returns:
            An :class:`OrderHistoryResult` containing the customer's order list.
        """
        # TODO: Implement internal REST API or DB call
        return OrderHistoryResult(success=True, history=[])

    def get_account_details(self, customer_id: str) -> AccountDetailsResult:
        """Return profile and account metadata from the internal system.

        Args:
            customer_id: Internal system customer identifier.

        Returns:
            An :class:`AccountDetailsResult` with the customer's account fields.
        """
        # TODO: Implement internal REST API or DB call
        return AccountDetailsResult(success=True, details={"email": "customer@example.com"})

    def get_billing_details(self, customer_id: str) -> BillingResult:
        """Return billing and payment information from the internal system.

        Args:
            customer_id: Internal system customer identifier.

        Returns:
            A :class:`BillingResult` containing billing status and payment details.
        """
        # TODO: Implement internal REST API or DB call
        return BillingResult(success=True, billing_info={"status": "paid"})

    def issue_refund(self, order_id: str, amount: float, reason: str, idempotency_key: str) -> RefundResult:
        """Submit a refund request to the internal system for the specified order.

        Args:
            order_id: Internal system order identifier.
            amount: The monetary amount to refund in the store's default currency.
            reason: Human-readable reason string for the refund.
            idempotency_key: Unique caller-generated key forwarded to the internal
                system to deduplicate retried refund requests.

        Returns:
            A :class:`RefundResult` with the internally-assigned refund ID and amount.
        """
        # TODO: Implement internal REST API or DB call using idempotency_key
        return RefundResult(success=True, refund_id=f"inhouse_{order_id}", amount=amount)

    def cancel_order(self, order_id: str, reason: str, idempotency_key: str) -> CancelResult:
        """Cancel an order via the internal system.

        Args:
            order_id: Internal system order identifier.
            reason: Human-readable reason for the cancellation.
            idempotency_key: Unique caller-generated key to deduplicate retried
                cancellation requests.

        Returns:
            A :class:`CancelResult` indicating whether the cancellation succeeded.
        """
        # TODO: Implement internal REST API or DB call using idempotency_key
        return CancelResult(success=True, cancelled=True)

    def update_shipping_address(self, order_id: str, new_address: Dict[str, Any], idempotency_key: str) -> AddressUpdateResult:
        """Update the shipping address on an order in the internal system.

        Args:
            order_id: Internal system order identifier.
            new_address: Dict of address fields accepted by the internal API
                (e.g. ``street``, ``city``, ``country``, ``postal_code``).
            idempotency_key: Unique caller-generated key to deduplicate retried
                address update requests.

        Returns:
            An :class:`AddressUpdateResult` indicating whether the update succeeded.
        """
        # TODO: Implement internal REST API or DB call using idempotency_key
        return AddressUpdateResult(success=True, updated=True)
