from .adapters.shopify_adapter import ShopifyAdapter
from .adapters.inhouse_adapter import InHouseAdapter

ADAPTER_REGISTRY = {
    "shopify": ShopifyAdapter,
    "inhouse": InHouseAdapter,
}

def build_adapter(adapter_key: str, config: dict):
    cls = ADAPTER_REGISTRY.get(adapter_key)
    if cls is None:
        raise ValueError(f"Unknown adapter_key: {adapter_key}")
    return cls(config=config)
