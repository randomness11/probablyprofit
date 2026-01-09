"""
Web Server

Launches FastAPI server alongside the agent loop.
"""

import uvicorn
import asyncio
from loguru import logger
from typing import Optional

from probablyprofit.web.app import create_app, set_agent_state
from probablyprofit.agent.base import BaseAgent


async def run_server_with_agent(
    agent: BaseAgent,
    agent_type: str,
    strategy_name: str,
    host: str = "0.0.0.0",
    port: int = 8000,
):
    """Run FastAPI server alongside agent loop."""

    # Set agent state for web access
    set_agent_state(agent, agent_type, strategy_name)

    # Create FastAPI app
    app = create_app()

    # Configure uvicorn
    config = uvicorn.Config(app, host=host, port=port, log_level="info", access_log=False)
    server = uvicorn.Server(config)

    # Run server and agent loop concurrently
    logger.info(f"🌐 Starting web dashboard on http://{host}:{port}")
    logger.info(f"📊 Dashboard: http://localhost:{port}")
    logger.info(f"📡 WebSocket: ws://localhost:{port}/ws")
    logger.info(f"🔌 API Docs: http://localhost:{port}/docs")

    try:
        # Run both server and agent in parallel
        await asyncio.gather(server.serve(), agent.run_loop())
    except KeyboardInterrupt:
        logger.info("Shutting down server and agent...")
    finally:
        agent.running = False
