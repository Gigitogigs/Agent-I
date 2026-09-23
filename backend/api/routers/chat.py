from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from backend.api.dependencies import get_db
from backend.api.schemas.chat import ChatRequest, ChatResponse
from backend.services.chat_service import process_chat_turn
from backend.api.dependencies import require_min_role
from backend.db.models.chat import Conversation

router = APIRouter(prefix="/workspaces", tags=["chat"])

@router.post(
    "/{workspace_id}/conversations/{conversation_id}/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    # Depending on requirements, chatting might be a public widget, 
    # but since it's the backend API, we might require some auth.
    # For now, we'll assume it's read-only+ or public depending on how the widget connects.
    # To match API-Contract read-only+ for stats, we'll just require read_only to test.
    dependencies=[Depends(require_min_role("read_only"))]
)
async def submit_chat_message(
    workspace_id: UUID,
    conversation_id: UUID,
    request: ChatRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Submits a customer message to the conversation and invokes the agent graph.
    """
    # 1. Validate conversation exists and belongs to workspace
    conv = await db.get(Conversation, conversation_id)
    if not conv or conv.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
        
    if conv.status != "open":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Conversation is {conv.status} and cannot accept new messages."
        )
        
    # 2. Process turn
    try:
        result = await process_chat_turn(
            db=db,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            message=request.message
        )
        return ChatResponse(
            response=result["response"],
            turn_id=result["turn_id"],
            subagent_results=result["subagent_results"]
        )
    except Exception as e:
        # In production we'd log the full traceback
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent error: {str(e)}"
        )
