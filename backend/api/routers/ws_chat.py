from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from jose import JWTError
import json
import logging

from backend.api.dependencies import get_db
from backend.core.security import decode_token
from backend.services.auth_service import get_user_by_id
from backend.db.models.chat import Conversation
from backend.api.ws_manager import manager
from backend.services.chat_service import process_chat_turn_streaming

router = APIRouter(prefix="/workspaces", tags=["chat_ws"])
logger = logging.getLogger(__name__)

@router.websocket("/{workspace_id}/conversations/{conversation_id}/ws")
async def chat_websocket(
    websocket: WebSocket,
    workspace_id: UUID,
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    # 1. Auth via Subprotocol
    sec_protocol = websocket.headers.get("sec-websocket-protocol", "")
    token = None
    for proto in sec_protocol.split(","):
        proto = proto.strip()
        if proto.startswith("access_token."):
            token = proto.replace("access_token.", "")
            break
            
    if not token:
        await websocket.close(code=4001, reason="Unauthorized: Missing token in subprotocol")
        return
        
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
             await websocket.close(code=4001, reason="Unauthorized: Invalid token type")
             return
        user_id = payload.get("sub")
        if not user_id:
             await websocket.close(code=4001, reason="Unauthorized: Invalid subject")
             return
        user = await get_user_by_id(db, user_id)
        if not user:
             await websocket.close(code=4001, reason="Unauthorized: User not found")
             return
             
        # Check workspace membership
        is_member = False
        for membership in user.workspaces:
             if membership.workspace_id == workspace_id:
                 is_member = True
                 break
        if not is_member:
             await websocket.close(code=4001, reason="Unauthorized: Not a member of this workspace")
             return
             
    except JWTError:
        await websocket.close(code=4001, reason="Unauthorized: Invalid token")
        return

    # 2. Check conversation
    conv = await db.get(Conversation, conversation_id)
    if not conv or conv.workspace_id != workspace_id:
        await websocket.close(code=4004, reason="Conversation not found")
        return
        
    if conv.status != "open":
        await websocket.close(code=4003, reason=f"Conversation is {conv.status}")
        return

    # 3. Accept with subprotocol
    await websocket.accept(subprotocol=f"access_token.{token}")
    await manager.connect(conversation_id, websocket)

    try:
        while True:
            text_data = await websocket.receive_text()
            try:
                data = json.loads(text_data)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "detail": "Invalid JSON"})
                continue
                
            msg_type = data.get("type")
            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue
                
            if msg_type == "message":
                content = data.get("content")
                if not content:
                    await websocket.send_json({"type": "error", "detail": "Message content cannot be empty"})
                    continue
                    
                # Stream the response back
                try:
                    await websocket.send_json({"type": "agent_status", "status": "thinking"})
                    async for event in process_chat_turn_streaming(db, workspace_id, conversation_id, content):
                        await websocket.send_json(event)
                except Exception as e:
                    logger.error(f"Error in chat streaming: {e}")
                    await websocket.send_json({"type": "error", "detail": "Agent error occurred"})
            else:
                await websocket.send_json({"type": "error", "detail": "Unknown message type"})
                
    except WebSocketDisconnect:
        manager.disconnect(conversation_id)
    except Exception as e:
        logger.error(f"Unexpected websocket error: {e}")
        manager.disconnect(conversation_id)
