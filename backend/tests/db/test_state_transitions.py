import pytest
from datetime import datetime, timezone
from sqlalchemy import select
from backend.db.models.user import User
from backend.db.models.workspace import Workspace
from backend.db.models.approvals import ApprovalRequest
from backend.db.models.knowledge import Document
from backend.db.models.chat import Conversation

@pytest.mark.asyncio
async def test_approval_request_lifecycle(db_session):
    """Test state transitions of ApprovalRequest."""
    ws = Workspace(name="State Test WS")
    db_session.add(ws)
    await db_session.flush()

    conv = Conversation(workspace_id=ws.id, status="open", channel="widget")
    db_session.add(conv)
    await db_session.flush()

    approval = ApprovalRequest(
        workspace_id=ws.id,
        conversation_id=conv.id,
        agent_id="agent-1",
        action_type="escalate",
        payload={"reason": "complex"},
        risk_level="high",
        status="pending"
    )
    db_session.add(approval)
    await db_session.flush()

    # Transition to approved
    approval.status = "approved"
    approval.resolved_at = datetime.now(timezone.utc)
    await db_session.flush()

    assert approval.resolved_at is not None
    assert approval.status == "approved"

@pytest.mark.asyncio
async def test_document_processing_states(db_session):
    """Test Document processing state flows and error handling."""
    ws = Workspace(name="Doc WS")
    user = User(email="doc@test.com", password_hash="hash")
    db_session.add_all([ws, user])
    await db_session.flush()

    doc = Document(
        workspace_id=ws.id,
        uploaded_by_user_id=user.id,
        filename="test.pdf",
        file_path="/tmp/test.pdf",
        file_type="application/pdf",
        file_size_bytes=1000,
        status="processing"
    )
    db_session.add(doc)
    await db_session.flush()

    # Simulate processing failure
    doc.status = "error"
    doc.error_message = "Failed to parse PDF"
    await db_session.flush()

    stmt = select(Document).where(Document.id == doc.id)
    result = await db_session.execute(stmt)
    saved_doc = result.scalar_one()

    assert saved_doc.status == "error"
    assert saved_doc.error_message == "Failed to parse PDF"
