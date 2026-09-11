from .schemas import (
    StockLevelResult,
    ReserveStockResult,
    UpdateStockCountResult
)
from .base import AdapterProtocol

class InHouseAdapter(AdapterProtocol):
    """
    Inventory adapter backed by the client's own internal infrastructure.

    Makes direct REST API calls or database queries to the client's proprietary
    inventory system rather than a third-party platform. This is the default
    adapter selected when ``ADAPTER_TYPE`` is not set to ``"shopify"``.

    Note: Unlike the order/account domain, no shared in-house client is used
    here yet; each adapter instance manages its own connection credentials.

    Args:
        api_base_url: Base URL of the internal inventory API
            (e.g. ``"https://inventory.internal.example.com/v1"``). Must not
            include a trailing slash.
        api_key: Secret key used to authenticate requests to the internal API.
    """

    def __init__(self, api_base_url: str, api_key: str):
        """Store connection details for use in every API call.

        Args:
            api_base_url: Base URL of the internal inventory REST API.
            api_key: API key for authenticating requests.
        """
        self.api_base_url = api_base_url
        self.api_key = api_key

    def get_stock_level(self, sku: str) -> StockLevelResult:
        """Return the available stock level for a SKU from the internal system.

        Args:
            sku: The product SKU to query.

        Returns:
            A :class:`StockLevelResult` with the available quantity and
            internal warehouse location identifiers.
        """
        # TODO: Implement in-house DB call
        return StockLevelResult(success=True, sku=sku, available_quantity=50)

    def reserve_stock(self, sku: str, quantity: int, idempotency_key: str) -> ReserveStockResult:
        """Reserve inventory units in the internal system to prevent overselling.

        Args:
            sku: The product SKU to reserve.
            quantity: Number of units to reserve.
            idempotency_key: Unique caller-generated key to prevent duplicate
                reservations if the request is retried after a network failure.

        Returns:
            A :class:`ReserveStockResult` with the internally-assigned reservation
            ID and the number of units reserved.
        """
        # TODO: Implement in-house DB call
        return ReserveStockResult(success=True, reservation_id=f"inhouse_{sku}", reserved_quantity=quantity)

    def update_stock_count(self, sku: str, new_count: int, reason: str, idempotency_key: str) -> UpdateStockCountResult:
        """Set the stock count for a SKU to an absolute value in the internal system.

        Args:
            sku: The product SKU whose stock count should be updated.
            new_count: The new absolute stock count to write.
            reason: Human-readable reason for the adjustment
                (e.g. ``"manual_correction"``, ``"shrinkage"``).
            idempotency_key: Unique caller-generated key to prevent the same
                count update being applied more than once on retry.

        Returns:
            An :class:`UpdateStockCountResult` indicating whether the count was
            successfully written to the internal system.
        """
        # TODO: Implement in-house DB call
        return UpdateStockCountResult(success=True, updated=True)
