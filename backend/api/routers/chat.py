from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from backend.api.dependencies import get_db
from typing import Optional
from backend.api.schemas.chat import ChatRequest, ChatResponse, ConversationListResponse, ConversationDetailOut
from backend.services.chat_service import process_chat_turn, list_conversations, get_conversation_detail
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
    dependencies=[Depends(require_min_role("read-only"))]
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


@router.get(
    "/{workspace_id}/conversations",
    response_model=ConversationListResponse,
    dependencies=[Depends(require_min_role("read-only"))]
)
async def get_conversations(
    workspace_id: UUID,
    status: Optional[str] = None,
    search: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
):
    """
    Returns a paginated list of conversations for a workspace.
    """
    cursor_date, cursor_id = None, None
    if cursor:
        try:
            parts = cursor.split(",")
            cursor_date = parts[0]
            cursor_id = UUID(parts[1])
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid cursor format")
            
    return await list_conversations(
        db=db,
        workspace_id=workspace_id,
        status=status,
        search=search,
        limit=limit,
        cursor_date=cursor_date,
        cursor_id=cursor_id
    )


@router.get(
    "/{workspace_id}/conversations/{conversation_id}",
    response_model=ConversationDetailOut,
    dependencies=[Depends(require_min_role("read-only"))]
)
async def get_conversation(
    workspace_id: UUID,
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Returns full details for a specific conversation including transcript.
    """
    detail = await get_conversation_detail(db, workspace_id, conversation_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Conversation not found")
        
    return detail
