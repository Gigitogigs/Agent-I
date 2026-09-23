import pytest
from sqlalchemy import select
from backend.db.models.chat import Conversation
from backend.db.models.workspace import Workspace

@pytest.mark.asyncio
async def test_tsvector_trigger_population(db_session):
    """Test that the PostgreSQL trigger automatically populates the search_vector."""
    ws = Workspace(name="TSVector WS")
    db_session.add(ws)
    await db_session.flush()

    # Create a conversation with some keywords
    conv = Conversation(
        workspace_id=ws.id,
        customer_name="Alice Smith",
        summary="login issue",
        customer_identifier="alice@example.com",
        status="open",
        channel="widget"
    )
    db_session.add(conv)
    await db_session.flush()
    await db_session.refresh(conv)

    # Note: SQLAlchemy's refresh might not immediately pull down the TSVector due to how it's mapped,
    # so we explicitly query the database to confirm it's not null and is searchable.
    
    # 1. Assert the raw column is not null in the DB
    stmt_check = select(Conversation.id).where(Conversation.search_vector.is_not(None), Conversation.id == conv.id)
    assert await db_session.scalar(stmt_check) == conv.id
    
    # 2. Assert it's searchable using PostgreSQL's match operator
    stmt_search = select(Conversation).where(
        Conversation.search_vector.match('alice', postgresql_regconfig='english')
    )
    result = await db_session.execute(stmt_search)
    found_conv = result.scalars().first()
    
    assert found_conv is not None
    assert found_conv.id == conv.id

    # 3. Test Updates
    # Update the summary with a new keyword
    conv.summary = "billing refund requested"
    await db_session.flush()
    
    # Assert the new keyword is searchable
    stmt_search_update = select(Conversation).where(
        Conversation.search_vector.match('refund', postgresql_regconfig='english')
    )
    result_update = await db_session.execute(stmt_search_update)
    found_conv_updated = result_update.scalars().first()
    
    assert found_conv_updated is not None
    assert found_conv_updated.id == conv.id
