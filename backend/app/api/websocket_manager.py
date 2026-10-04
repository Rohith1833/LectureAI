import asyncio
from typing import Dict, List
from fastapi import WebSocket
from loguru import logger

class ConnectionManager:
    def __init__(self):
        # Maps upload_id to list of active websockets
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, upload_id: str):
        await websocket.accept()
        if upload_id not in self.active_connections:
            self.active_connections[upload_id] = []
        self.active_connections[upload_id].append(websocket)
        logger.debug(f"WebSocket connected for upload {upload_id}")

    def disconnect(self, websocket: WebSocket, upload_id: str):
        if upload_id in self.active_connections:
            if websocket in self.active_connections[upload_id]:
                self.active_connections[upload_id].remove(websocket)
            if not self.active_connections[upload_id]:
                del self.active_connections[upload_id]
        logger.debug(f"WebSocket disconnected for upload {upload_id}")

    async def broadcast_to_upload(self, upload_id: str, message: dict):
        """Send a JSON message to all clients listening to a specific upload_id."""
        if upload_id in self.active_connections:
            websockets = self.active_connections[upload_id].copy()
            for connection in websockets:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.warning(f"Failed to send to websocket: {e}")
                    self.disconnect(connection, upload_id)

manager = ConnectionManager()
