from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class BaseToolResult(BaseModel):
    """Base response shape returned by every inventory MCP tool, regardless of backend.

    Attributes:
        success: ``True`` if the operation completed without error, ``False`` otherwise.
        error: Human-readable error message populated only when ``success`` is ``False``.
    """

    success: bool
    error: Optional[str] = None

class StockLevelResult(BaseToolResult):
    """Result of a ``get_stock_level`` call.

    Attributes:
        sku: The product SKU that was queried.
        available_quantity: Current sellable stock count across all locations.
        warehouse_locations: List of warehouse or location identifiers where
            this SKU is stocked.
    """

    sku: Optional[str] = None
    available_quantity: Optional[int] = None
    warehouse_locations: Optional[List[str]] = None

class ReserveStockResult(BaseToolResult):
    """Result of a ``reserve_stock`` call.

    Attributes:
        reservation_id: Unique identifier for the stock reservation; must be
            held by the caller until the reservation is released or fulfilled.
        reserved_quantity: The number of units successfully reserved.
    """

    reservation_id: Optional[str] = None
    reserved_quantity: Optional[int] = None

class UpdateStockCountResult(BaseToolResult):
    """Result of an ``update_stock_count`` call.

    Attributes:
        updated: ``True`` if the stock count was successfully written to the backend.
    """

    updated: bool = False
