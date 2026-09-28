from typing import Dict
from uuid import UUID
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        # Maps conversation_id to a WebSocket connection
        self.active_connections: Dict[UUID, WebSocket] = {}

    async def connect(self, conversation_id: UUID, websocket: WebSocket):
        self.active_connections[conversation_id] = websocket

    def disconnect(self, conversation_id: UUID):
        if conversation_id in self.active_connections:
            del self.active_connections[conversation_id]

    async def send_json(self, conversation_id: UUID, data: dict):
        if conversation_id in self.active_connections:
            websocket = self.active_connections[conversation_id]
            await websocket.send_json(data)

manager = ConnectionManager()
