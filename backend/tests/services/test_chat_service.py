import pytest
from uuid import uuid4
import sys
from unittest.mock import MagicMock
sys.modules['langchain_postgres'] = MagicMock()
sys.modules['langchain_postgres.vectorstores'] = MagicMock()

from backend.services.chat_service import _get_active_connector
from backend.db.models.settings import WorkspaceIntegration
from backend.core.security import encrypt_secret
import json

@pytest.mark.asyncio
async def test_get_active_connector(db_session):
    ws_id = uuid4()
    # Add fake workspace to avoid FK violations, but we don't strictly have a Workspace fixture here easily accessible without setup_test_workspace,
    # wait let's just use a MagicMock for the session or create one.
    
    # Actually, we can test by inserting a mock integration.
    # To do this safely, we will just use a mock db session.
    class MockResult:
        def __init__(self, data):
            self.data = data
        def scalars(self):
            return self
        def all(self):
            return self.data
            
    class MockDb:
        async def execute(self, stmt):
            cfg = {"encrypted_payload": encrypt_secret(json.dumps({"store_url": "foo"}))}
            integration = WorkspaceIntegration(
                workspace_id=ws_id,
                integration_type="shopify",
                domain="order_account",
                is_primary=True,
                status="active",
                config=cfg
            )
            return MockResult([integration])

    mock_db = MockDb()
    res = await _get_active_connector(mock_db, ws_id, "order_account")
    assert res is not None
    assert res["adapter_key"] == "shopify"
    assert res["transport"] == "builtin"
    assert res["config"]["store_url"] == "foo"

@pytest.mark.asyncio
async def test_get_active_connector_custom_mcp(db_session):
    ws_id = uuid4()
    
    class MockDb:
        async def execute(self, stmt):
            cfg = {"encrypted_payload": encrypt_secret(json.dumps({"server_url": "http://foo"}))}
            integration = WorkspaceIntegration(
                workspace_id=ws_id,
                integration_type="custom_mcp",
                domain="order_account",
                is_primary=True,
                status="active",
                config=cfg
            )
            return MockResult([integration])

    class MockResult:
        def __init__(self, data):
            self.data = data
        def scalars(self):
            return self
        def all(self):
            return self.data

    mock_db = MockDb()
    res = await _get_active_connector(mock_db, ws_id, "order_account")
    assert res is not None
    assert res["adapter_key"] is None
    assert res["transport"] == "remote_mcp"
    assert res["config"]["server_url"] == "http://foo"
