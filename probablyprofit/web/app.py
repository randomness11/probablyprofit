"""
FastAPI Application

Main FastAPI app for the probablyprofit dashboard.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from dataclasses import dataclass
from datetime import datetime

from probablyprofit.agent.base import BaseAgent
from probablyprofit.web.api.routes import router as api_router
from probablyprofit.web.api.websocket import websocket_endpoint


@dataclass
class AgentState:
    """Global agent state for web access."""

    agent: BaseAgent
    agent_type: str
    strategy_name: str
    start_time: datetime

    @property
    def uptime_seconds(self) -> float:
        return (datetime.now() - self.start_time).total_seconds()


# Global agent state
_agent_state: Optional[AgentState] = None


def create_app() -> FastAPI:
    """Create FastAPI application."""
    app = FastAPI(
        title="probablyprofit Dashboard API",
        description="Real-time trading bot monitoring and control",
        version="1.0.0",
    )

    # CORS middleware for React frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",  # Vite dev server
            "http://localhost:3000",  # Create React App
            "http://localhost:8000",  # Same origin
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routes
    app.include_router(api_router)

    # WebSocket endpoint
    app.add_websocket_route("/ws", websocket_endpoint)

    @app.get("/")
    async def root():
        return {"message": "probablyprofit Dashboard API", "version": "1.0.0"}

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    return app


def set_agent_state(agent: BaseAgent, agent_type: str, strategy_name: str):
    """Set global agent state for web access."""
    global _agent_state
    _agent_state = AgentState(
        agent=agent,
        agent_type=agent_type,
        strategy_name=strategy_name,
        start_time=datetime.now(),
    )


def get_agent_state() -> Optional[AgentState]:
    """Get global agent state."""
    return _agent_state
