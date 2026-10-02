import pytest
from support_system.mcp_servers.shared.adapter_registry import build_adapter
from support_system.mcp_servers.shared.adapters.shopify_adapter import ShopifyAdapter
from support_system.mcp_servers.shared.adapters.inhouse_adapter import InHouseAdapter

def test_build_adapter_shopify():
    config = {"store_url": "foo", "access_token": "bar"}
    adapter = build_adapter("shopify", config)
    assert isinstance(adapter, ShopifyAdapter)
    assert adapter.store_url == "foo"
    assert adapter.access_token == "bar"

def test_build_adapter_inhouse():
    config = {"api_base_url": "foo", "api_key": "bar"}
    adapter = build_adapter("inhouse", config)
    assert isinstance(adapter, InHouseAdapter)
    assert adapter.api_base_url == "foo"
    assert adapter.api_key == "bar"

def test_build_adapter_invalid():
    with pytest.raises(ValueError, match="Unknown adapter_key: invalid"):
        build_adapter("invalid", {})
