from typing import Protocol, runtime_checkable
from .schemas import (
    StockLevelResult,
    ReserveStockResult,
    UpdateStockCountResult
)

@runtime_checkable
class AdapterProtocol(Protocol):
    """
    Structural interface that every inventory backend adapter must satisfy.

    Both ``ShopifyAdapter`` and ``InHouseAdapter`` implement this protocol so
    that ``server.py`` can delegate to either backend transparently. The server
    selects the concrete adapter at startup via the ``ADAPTER_TYPE`` environment
    variable.

    All mutating operations (``reserve_stock``, ``update_stock_count``) require
    an ``idempotency_key`` so that callers can safely retry on network failure
    without creating duplicate reservations or applying the same count update
    twice.
    """

    def get_stock_level(self, sku: str) -> StockLevelResult:
        """Return the current available stock level for a SKU.

        Args:
            sku: The product stock-keeping unit identifier to query.

        Returns:
            A :class:`StockLevelResult` with the available quantity and warehouse
            locations for the given SKU.
        """
        ...

    # Mutating actions MUST accept an idempotency_key
    def reserve_stock(self, sku: str, quantity: int, idempotency_key: str) -> ReserveStockResult:
        """Reserve a quantity of a SKU to prevent overselling.

        Args:
            sku: The product SKU to reserve.
            quantity: Number of units to reserve.
            idempotency_key: Unique caller-generated key to prevent duplicate
                reservations if the request is retried after a network failure.

        Returns:
            A :class:`ReserveStockResult` with the reservation ID and the number
            of units actually reserved.
        """
        ...

    def update_stock_count(self, sku: str, new_count: int, reason: str, idempotency_key: str) -> UpdateStockCountResult:
        """Overwrite the stock count for a SKU with a new absolute value.

        Args:
            sku: The product SKU whose stock count should be updated.
            new_count: The new absolute stock count to set.
            reason: Human-readable reason for the stock adjustment
                (e.g. ``"manual_correction"``, ``"shrinkage"``).
            idempotency_key: Unique caller-generated key to prevent the same
                count update being applied more than once on retry.

        Returns:
            An :class:`UpdateStockCountResult` indicating whether the count was
            successfully written to the backend.
        """
        ...
