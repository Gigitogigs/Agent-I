# Order & Account MCP Server

This MCP server acts as the central interface for all order- and account-related actions in the support system. It defines the **canonical tool contract** that the `action_agent` consumes.

## Canonical Contract

| Tool | Parameters | Returns |
|---|---|---|
| `get_order_status` | `order_id: str` | `OrderStatusResult` |
| `get_order_history` | `customer_id: str` | `OrderHistoryResult` |
| `get_account_details` | `customer_id: str` | `AccountDetailsResult` |
| `get_billing_details` | `customer_id: str` | `BillingResult` |
| `issue_refund` | `order_id: str, amount: float, reason: str, idempotency_key: str` | `RefundResult` |
| `cancel_order` | `order_id: str, reason: str, idempotency_key: str` | `CancelResult` |
| `update_shipping_address` | `order_id: str, new_address: dict, idempotency_key: str` | `AddressUpdateResult` |

## Adapters

This server handles backend variability via the **Adapter Pattern**. 
The `action_agent` always calls the canonical tools above, and the MCP server dispatches them to the configured adapter:

- `ShopifyAdapter`: For clients using Shopify.
- `InHouseAdapter`: For clients with custom internal APIs.

Configure the active adapter via the `ADAPTER_TYPE` environment variable (`shopify` or `inhouse`).
