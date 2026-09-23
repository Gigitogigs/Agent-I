"""Inventory MCP server entry-point.

Exposes three MCP tools for querying and managing product inventory:

- :func:`get_stock_level` — query current available units for a SKU.
- :func:`reserve_stock` — hold units to prevent overselling.
- :func:`update_stock_count` — overwrite the stock count with a new absolute value.

The concrete backend adapter (Shopify or in-house) is selected at startup via
the ``ADAPTER_TYPE`` environment variable (default: ``"inhouse"``).
"""
import os
import json
from mcp.server.fastmcp import FastMCP as MCPServer
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.shopify_client import SharedShopifyClient
from adapters.shopify_adapter import ShopifyAdapter
from adapters.inhouse_adapter import InHouseAdapter
from adapters.base import AdapterProtocol

mcp = MCPServer("inventory-mcp")

# --- Adapter Selection ---
ADAPTER_TYPE = os.getenv("ADAPTER_TYPE", "inhouse")

adapter: AdapterProtocol

if ADAPTER_TYPE == "shopify":
    shopify_client = SharedShopifyClient(
        shop_url=os.getenv("SHOPIFY_SHOP_URL", ""),
        access_token=os.getenv("SHOPIFY_ACCESS_TOKEN", "")
    )
    adapter = ShopifyAdapter(client=shopify_client)
else:
    # Notice we don't use a shared inhouse client here yet per the instructions
    adapter = InHouseAdapter(
        api_base_url=os.getenv("INHOUSE_API_BASE_URL", ""),
        api_key=os.getenv("INHOUSE_API_KEY", "")
    )

# --- MCP Tool Exposures ---
@mcp.tool()
def get_stock_level(sku: str) -> str:
    """Return the current available stock level for a product SKU.

    Args:
        sku: The product stock-keeping unit identifier to query
            (e.g. ``"SKU-ABC-123"``).

    Returns:
        JSON-serialised :class:`~adapters.schemas.StockLevelResult` containing
        the available quantity and warehouse location list.
    """
    result = adapter.get_stock_level(sku)
    return result.model_dump_json()

@mcp.tool()
def reserve_stock(sku: str, quantity: int, idempotency_key: str) -> str:
    """Reserve inventory stock to prevent a SKU from being oversold.

    Args:
        sku: The product SKU to reserve units for.
        quantity: The number of units to hold.
        idempotency_key: Unique caller-generated key (e.g. a UUID) that allows
            this operation to be safely retried without creating duplicate
            reservations.

    Returns:
        JSON-serialised :class:`~adapters.schemas.ReserveStockResult` with the
        assigned reservation ID and the number of units actually reserved.
    """
    result = adapter.reserve_stock(sku, quantity, idempotency_key)
    return result.model_dump_json()

@mcp.tool()
def update_stock_count(sku: str, new_count: int, reason: str, idempotency_key: str) -> str:
    """Overwrite the stock count for a SKU with a new absolute value.

    Args:
        sku: The product SKU to update.
        new_count: The new absolute stock count to set.
        reason: Human-readable reason for the adjustment
            (e.g. ``"inventory_received"``, ``"manual_correction"``,
            ``"shrinkage"``).
        idempotency_key: Unique caller-generated key that prevents the same
            stock update from being applied more than once on retry.

    Returns:
        JSON-serialised :class:`~adapters.schemas.UpdateStockCountResult`
        indicating whether the count was successfully written.
    """
    result = adapter.update_stock_count(sku, new_count, reason, idempotency_key)
    return result.model_dump_json()

if __name__ == "__main__":
    mcp.run()
