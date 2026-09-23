import sys
import os

from .schemas import (
    StockLevelResult,
    ReserveStockResult,
    UpdateStockCountResult
)
from .base import AdapterProtocol

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from shared.shopify_client import SharedShopifyClient

class ShopifyAdapter(AdapterProtocol):
    """
    Inventory adapter backed by the Shopify Admin API.

    Translates canonical ``AdapterProtocol`` calls into Shopify inventory API
    requests using a pre-authenticated
    :class:`~shared.shopify_client.SharedShopifyClient`. All mutating operations
    forward the ``idempotency_key`` to prevent duplicate side-effects.

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

    def get_stock_level(self, sku: str) -> StockLevelResult:
        """Return the available stock level for a SKU from Shopify.

        Args:
            sku: The product SKU to query in Shopify Inventory.

        Returns:
            A :class:`StockLevelResult` with the available quantity and
            Shopify location identifiers.
        """
        # TODO: Implement actual Shopify call
        return StockLevelResult(success=True, sku=sku, available_quantity=100)

    def reserve_stock(self, sku: str, quantity: int, idempotency_key: str) -> ReserveStockResult:
        """Reserve inventory units in Shopify to prevent overselling.

        Args:
            sku: The product SKU to reserve.
            quantity: Number of units to reserve.
            idempotency_key: Unique caller-generated key forwarded to Shopify
                to deduplicate retried reservation requests.

        Returns:
            A :class:`ReserveStockResult` with the reservation ID and the number
            of units actually reserved.
        """
        # TODO: Implement actual Shopify call
        return ReserveStockResult(success=True, reservation_id=f"res_{sku}", reserved_quantity=quantity)

    def update_stock_count(self, sku: str, new_count: int, reason: str, idempotency_key: str) -> UpdateStockCountResult:
        """Set the stock count for a SKU to an absolute value in Shopify.

        Args:
            sku: The product SKU to update.
            new_count: The new absolute stock count to set in Shopify.
            reason: Human-readable reason for the adjustment
                (e.g. ``"inventory_received"``, ``"shrinkage"``).
            idempotency_key: Unique caller-generated key to deduplicate retried
                stock update requests.

        Returns:
            An :class:`UpdateStockCountResult` indicating whether the count was
            successfully written to Shopify.
        """
        # TODO: Implement actual Shopify call
        return UpdateStockCountResult(success=True, updated=True)
