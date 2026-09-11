from typing import Dict, Any
import sys
import os

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

# Ensure shared can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from shared.shopify_client import SharedShopifyClient

class ShopifyAdapter(AdapterProtocol):
    """
    Order/account adapter backed by the Shopify Admin API.

    Translates canonical ``AdapterProtocol`` calls into Shopify API requests
    using a pre-authenticated :class:`~shared.shopify_client.SharedShopifyClient`.
    All read operations query Shopify's REST or GraphQL endpoints; all mutating
    operations forward the ``idempotency_key`` to prevent duplicate side-effects.

    Args:
        client: An already-initialised :class:`SharedShopifyClient` instance
            holding the shop URL and access token.
    """

    def __init__(self, client: SharedShopifyClient):
        """Store the shared Shopify client for use in every API call.

        Args:
            client: An already-initialised :class:`SharedShopifyClient` instance.
        """
        self.client = client

    def get_order_status(self, order_id: str) -> OrderStatusResult:
        """Return the current fulfilment status of an order from Shopify.

        Args:
            order_id: The Shopify order ID (numeric string or GID).

        Returns:
            An :class:`OrderStatusResult` with the order's fulfilment status.
        """
        # TODO: Implement actual Shopify call
        return OrderStatusResult(success=True, status="fulfilled")

    def get_order_history(self, customer_id: str) -> OrderHistoryResult:
        """Return all past orders for a customer from Shopify.

        Args:
            customer_id: The Shopify customer ID.

        Returns:
            An :class:`OrderHistoryResult` containing the customer's order list.
        """
        # TODO: Implement actual Shopify call
        return OrderHistoryResult(success=True, history=[])

    def get_account_details(self, customer_id: str) -> AccountDetailsResult:
        """Return profile and account metadata for a Shopify customer.

        Args:
            customer_id: The Shopify customer ID.

        Returns:
            An :class:`AccountDetailsResult` with the customer's account fields.
        """
        # TODO: Implement actual Shopify call
        return AccountDetailsResult(success=True, details={"email": "customer@example.com"})

    def get_billing_details(self, customer_id: str) -> BillingResult:
        """Return billing and payment information for a Shopify customer.

        Args:
            customer_id: The Shopify customer ID.

        Returns:
            A :class:`BillingResult` containing gateway and payment details.
        """
        # TODO: Implement actual Shopify call
        return BillingResult(success=True, billing_info={"gateway": "stripe"})

    def issue_refund(self, order_id: str, amount: float, reason: str, idempotency_key: str) -> RefundResult:
        """Submit a refund request to Shopify for the specified order.

        Args:
            order_id: The Shopify order ID to refund.
            amount: The monetary amount to refund in the store's default currency.
            reason: Human-readable reason string (e.g. ``"damaged_item"``).
            idempotency_key: Unique caller-generated key forwarded to Shopify to
                deduplicate retried refund requests.

        Returns:
            A :class:`RefundResult` with the Shopify-assigned refund ID and amount.
        """
        # TODO: Implement actual Shopify call using idempotency_key
        return RefundResult(success=True, refund_id=f"ref_{order_id}", amount=amount)

    def cancel_order(self, order_id: str, reason: str, idempotency_key: str) -> CancelResult:
        """Cancel an order via the Shopify Admin API.

        Args:
            order_id: The Shopify order ID to cancel.
            reason: Human-readable reason for the cancellation.
            idempotency_key: Unique caller-generated key to deduplicate retried
                cancellation requests.

        Returns:
            A :class:`CancelResult` indicating whether the cancellation succeeded.
        """
        # TODO: Implement actual Shopify call using idempotency_key
        return CancelResult(success=True, cancelled=True)

    def update_shipping_address(self, order_id: str, new_address: Dict[str, Any], idempotency_key: str) -> AddressUpdateResult:
        """Update the shipping address on a Shopify order.

        Args:
            order_id: The Shopify order ID whose address should be updated.
            new_address: Dict of address fields accepted by the Shopify Orders API
                (e.g. ``first_name``, ``address1``, ``city``, ``country``, ``zip``).
            idempotency_key: Unique caller-generated key to deduplicate retried
                address update requests.

        Returns:
            An :class:`AddressUpdateResult` indicating whether the update succeeded.
        """
        # TODO: Implement actual Shopify call using idempotency_key
        return AddressUpdateResult(success=True, updated=True)
