# backend/core/connectors.py
#
# Single source of truth for every connector type the platform supports.
# Mirrors the shape of backend/core/providers.py::PROVIDER_CATALOG.
# Adding a new connector = adding one entry here + one adapter class.
# No other file should ever hardcode a connector-type string literal again;
# always look it up through CONNECTOR_CATALOG.

CONNECTOR_CATALOG = {
    "shopify": {
        "display_name": "Shopify",
        "domains": ["order_account", "inventory"],
        "transport": "builtin",
        "adapter_key": "shopify",
        "config_schema": {
            "store_url":   {"type": "string", "required": True, "secret": False},
            "access_token":{"type": "string", "required": True, "secret": True},
        },
    },
    "inhouse": {
        "display_name": "In-House API",
        "domains": ["order_account", "inventory"],
        "transport": "builtin",
        "adapter_key": "inhouse",
        "config_schema": {
            "api_base_url": {"type": "string", "required": True, "secret": False},
            "api_key":      {"type": "string", "required": True, "secret": True},
        },
    },
    "zendesk": {
        "display_name": "Zendesk",
        "domains": ["ticketing"],
        "transport": "builtin",
        "adapter_key": None,
        "config_schema": {
            "subdomain": {"type": "string", "required": True, "secret": False},
            "email":     {"type": "string", "required": True, "secret": False},
            "api_token": {"type": "string", "required": True, "secret": True},
        },
    },
    "custom_mcp": {
        "display_name": "Custom MCP Server",
        "domains": ["order_account", "inventory"],
        "transport": "remote_mcp",
        "adapter_key": None,
        "config_schema": {
            "server_url": {"type": "string", "required": True, "secret": False},
            "auth_token": {"type": "string", "required": False, "secret": True},
        },
    },
}
