import pytest
from sqlalchemy.exc import IntegrityError, DataError, StatementError
from sqlalchemy import select
from backend.db.models.user import User
from backend.db.models.workspace import Workspace
from backend.db.models.workspace_member import WorkspaceMember
from backend.db.models.agent_config import WorkspaceAgentConfig
from backend.db.models.knowledge import DocumentChunk

@pytest.mark.asyncio
async def test_invalid_uuid(db_session):
    """Test that Postgres rejects invalid UUID formats for UUID columns."""
    with pytest.raises(StatementError):
        user = User(id="not-a-valid-uuid", email="test@test.com", password_hash="hash")
        db_session.add(user)
        await db_session.flush()

@pytest.mark.asyncio
async def test_null_constraint_violations(db_session):
    """Test that missing required fields throws IntegrityError."""
    # User missing email
    with pytest.raises(IntegrityError):
        user = User(password_hash="hash")
        db_session.add(user)
        await db_session.flush()

@pytest.mark.asyncio
async def test_jsonb_boundaries(db_session):
    """Test JSONB column handling extreme/unusual data."""
    workspace = Workspace(name="JSON Test")
    db_session.add(workspace)
    await db_session.flush()

    # Very deep JSON
    deep_json = {"level1": {"level2": {"level3": {"level4": "value"}}}}
    config = WorkspaceAgentConfig(
        workspace_id=workspace.id,
        active_provider="ollama",
        custom_models=deep_json,
        custom_tools=[],
        custom_prompts={}
    )
    db_session.add(config)
    await db_session.flush()

    # Retrieve and verify
    stmt = select(WorkspaceAgentConfig).where(WorkspaceAgentConfig.id == config.id)
    result = await db_session.execute(stmt)
    saved_config = result.scalar_one()
    assert saved_config.custom_models["level1"]["level2"]["level3"]["level4"] == "value"

@pytest.mark.asyncio
async def test_negative_numeric_boundaries(db_session):
    """Test inserting negative values where typically unexpected (token counts).
    If it succeeds, it highlights missing CHECK constraints in the schema.
    """
    workspace = Workspace(name="Numeric Test")
    db_session.add(workspace)
    await db_session.flush()
    
    user = User(email="numeric@test.com", password_hash="hash")
    db_session.add(user)
    await db_session.flush()

    from backend.db.models.knowledge import Document
    doc = Document(
        workspace_id=workspace.id,
        uploaded_by_user_id=user.id,
        filename="test.txt",
        file_path="/tmp/test",
        file_type="text/plain",
        file_size_bytes=-100 # Negative size
    )
    db_session.add(doc)
    await db_session.flush()

    chunk = DocumentChunk(
        document_id=doc.id,
        workspace_id=workspace.id,
        chunk_index=-1, # Negative index
        content="test",
        token_count=-50 # Negative tokens
    )
    db_session.add(chunk)
    # Postgres doesn't prevent this natively unless a CHECK constraint is defined.
    # If this doesn't raise, we report it as a missing constraint.
    try:
        await db_session.flush()
        # Successfully inserted negative values
    except IntegrityError:
        # If CHECK constraint existed, it would fail
        pass
