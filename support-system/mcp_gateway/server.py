import os
from mcp.server.mcpserver import MCPServer
import json

from .adapters.shopify_adapter import ShopifyAdapter
from .adapters.inhouse_adapter import InHouseAdapter

mcp = MCPServer("order-account-mcp")

# --- Adapter Selection ---
ADAPTER_TYPE = os.getenv("ADAPTER_TYPE", "inhouse")

if ADAPTER_TYPE == "shopify":
    adapter = ShopifyAdapter(
        shop_url=os.getenv("SHOPIFY_SHOP_URL", ""),
        access_token=os.getenv("SHOPIFY_ACCESS_TOKEN", "")
    )
else:
    adapter = InHouseAdapter(
        api_base_url=os.getenv("INHOUSE_API_BASE_URL", ""),
        api_key=os.getenv("INHOUSE_API_KEY", "")
    )

# --- MCP Tool Exposures ---
@mcp.tool()
def get_order_status(order_id: str) -> str:
    """Fetch the status of an order."""
    result = adapter.get_order_status(order_id)
    return result.model_dump_json()

@mcp.tool()
def issue_refund(order_id: str, amount: float, reason: str) -> str:
    """Process a refund for a given order."""
    result = adapter.issue_refund(order_id, amount, reason)
    return result.model_dump_json()

@mcp.tool()
def cancel_order(order_id: str, reason: str) -> str:
    """Cancel a given order."""
    result = adapter.cancel_order(order_id, reason)
    return result.model_dump_json()

@mcp.tool()
def update_shipping_address(order_id: str, new_address: str) -> str:
    """Update the shipping address for a given order. Note: new_address should be a JSON string of the address."""
    address_dict = json.loads(new_address)
    result = adapter.update_shipping_address(order_id, address_dict)
    return result.model_dump_json()

@mcp.tool()
def get_billing_details(customer_id: str) -> str:
    """Fetch the billing details for a customer."""
    result = adapter.get_billing_details(customer_id)
    return result.model_dump_json()

if __name__ == "__main__":
    mcp.run()
