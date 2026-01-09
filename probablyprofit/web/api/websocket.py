"""
WebSocket Manager

Manages WebSocket connections for real-time updates.
"""

from fastapi import WebSocket, WebSocketDisconnect
from typing import Set
import json
from loguru import logger


class ConnectionManager:
    """Manages WebSocket connections."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        """Accept new connection."""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Remove connection."""
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast message to all connections."""
        if not self.active_connections:
            return

        data = json.dumps(message, default=str)
        disconnected = set()

        for connection in self.active_connections:
            try:
                await connection.send_text(data)
            except Exception as e:
                logger.warning(f"Failed to send to WebSocket: {e}")
                disconnected.add(connection)

        # Clean up disconnected clients
        self.active_connections -= disconnected


# Global connection manager
manager = ConnectionManager()


async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    await manager.connect(websocket)

    try:
        while True:
            # Keep connection alive (client can send ping)
            data = await websocket.receive_text()

            # Handle client messages (e.g., subscribe to specific events)
            try:
                message = json.loads(data)
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


# Event broadcasting functions (called from agent loop)

async def broadcast_trade(trade: dict):
    """Broadcast new trade event."""
    await manager.broadcast({"type": "trade", "data": trade})


async def broadcast_decision(decision: dict):
    """Broadcast new decision event."""
    await manager.broadcast({"type": "decision", "data": decision})


async def broadcast_observation(observation: dict):
    """Broadcast new observation event."""
    await manager.broadcast({"type": "observation", "data": observation})
