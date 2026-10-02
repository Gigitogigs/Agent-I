import pytest
from backend.core.connectors import CONNECTOR_CATALOG

def test_connector_catalog_entries():
    for key, entry in CONNECTOR_CATALOG.items():
        assert "display_name" in entry, f"Missing display_name for {key}"
        assert "domains" in entry, f"Missing domains for {key}"
        assert isinstance(entry["domains"], list), f"domains must be list for {key}"
        assert "transport" in entry, f"Missing transport for {key}"
        assert "config_schema" in entry, f"Missing config_schema for {key}"
