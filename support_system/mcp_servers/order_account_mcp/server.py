"""Order & Account MCP server entry-point.

Exposes seven MCP tools covering order and customer account operations:

- :func:`get_order_status` — fetch the current fulfilment status of an order.
- :func:`get_order_history` — retrieve a customer's past orders.
- :func:`get_account_details` — retrieve a customer's profile information.
- :func:`get_billing_details` — retrieve a customer's billing/payment info.
- :func:`issue_refund` — process a monetary refund for an order.
- :func:`cancel_order` — cancel an unfulfilled order.
- :func:`update_shipping_address` — change the delivery address on an order.

The concrete backend adapter (Shopify or in-house) is selected at startup via
the ``ADAPTER_TYPE`` environment variable (default: ``"inhouse"``).
"""
import os
import json
from mcp.server.fastmcp import FastMCP as MCPServer

from adapters.shopify_adapter import ShopifyAdapter
from adapters.inhouse_adapter import InHouseAdapter
from adapters.base import AdapterProtocol

mcp = MCPServer("order-account-mcp")

import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.shopify_client import SharedShopifyClient

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
    adapter = InHouseAdapter(
        api_base_url=os.getenv("INHOUSE_API_BASE_URL", ""),
        api_key=os.getenv("INHOUSE_API_KEY", "")
    )

# --- MCP Tool Exposures ---
@mcp.tool()
def get_order_status(order_id: str) -> str:
    """Return the current fulfilment status of an order.

    Args:
        order_id: Platform-specific unique order identifier.

    Returns:
        JSON-serialised :class:`~adapters.schemas.OrderStatusResult` with the
        order's current status string (e.g. ``"fulfilled"``, ``"processing"``).
    """
    result = adapter.get_order_status(order_id)
    return result.model_dump_json()

@mcp.tool()
def get_order_history(customer_id: str) -> str:
    """Return the full order history for a customer.

    Args:
        customer_id: Platform-specific unique customer identifier.

    Returns:
        JSON-serialised :class:`~adapters.schemas.OrderHistoryResult` containing
        a list of the customer's past order records.
    """
    result = adapter.get_order_history(customer_id)
    return result.model_dump_json()

@mcp.tool()
def get_account_details(customer_id: str) -> str:
    """Return profile and account metadata for a customer.

    Args:
        customer_id: Platform-specific unique customer identifier.

    Returns:
        JSON-serialised :class:`~adapters.schemas.AccountDetailsResult` with the
        customer's account fields (e.g. email, name, loyalty tier).
    """
    result = adapter.get_account_details(customer_id)
    return result.model_dump_json()

@mcp.tool()
def get_billing_details(customer_id: str) -> str:
    """Return billing and payment information for a customer.

    Args:
        customer_id: Platform-specific unique customer identifier.

    Returns:
        JSON-serialised :class:`~adapters.schemas.BillingResult` containing the
        customer's payment gateway and billing address details.
    """
    result = adapter.get_billing_details(customer_id)
    return result.model_dump_json()

@mcp.tool()
def issue_refund(order_id: str, amount: float, reason: str, idempotency_key: str) -> str:
    """Process a refund for a given order.

    Args:
        order_id: Platform-specific unique order identifier.
        amount: The monetary amount to refund in the store's default currency.
        reason: Human-readable reason for the refund (e.g. ``"damaged_item"``,
            ``"wrong_item_sent"``).
        idempotency_key: Unique caller-generated key (e.g. a UUID) that prevents
            duplicate refunds if the request is retried after a network failure.

    Returns:
        JSON-serialised :class:`~adapters.schemas.RefundResult` with the
        assigned refund ID and the confirmed refunded amount.
    """
    result = adapter.issue_refund(order_id, amount, reason, idempotency_key)
    return result.model_dump_json()

@mcp.tool()
def cancel_order(order_id: str, reason: str, idempotency_key: str) -> str:
    """Cancel an order that has not yet been fulfilled.

    Args:
        order_id: Platform-specific unique order identifier.
        reason: Human-readable reason for the cancellation.
        idempotency_key: Unique caller-generated key to prevent duplicate
            cancellations if the request is retried after a network failure.

    Returns:
        JSON-serialised :class:`~adapters.schemas.CancelResult` indicating
        whether the cancellation was applied successfully.
    """
    result = adapter.cancel_order(order_id, reason, idempotency_key)
    return result.model_dump_json()

@mcp.tool()
def update_shipping_address(order_id: str, new_address: dict, idempotency_key: str) -> str:
    """Update the shipping address on an existing order.

    Args:
        order_id: Platform-specific unique order identifier.
        new_address: Dictionary encoding the new address fields. Expected keys
            vary by backend but typically include ``street``, ``city``,
            ``country``, and ``postal_code``.
        idempotency_key: Unique caller-generated key to prevent the same address
            update from being applied more than once on retry.

    Returns:
        JSON-serialised :class:`~adapters.schemas.AddressUpdateResult`
        indicating whether the address was successfully updated.
    """
    result = adapter.update_shipping_address(order_id, new_address, idempotency_key)
    return result.model_dump_json()

if __name__ == "__main__":
    mcp.run()
