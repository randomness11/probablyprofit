"""
Web Dashboard

FastAPI server for real-time monitoring and control of trading agents.
"""

from probablyprofit.web.app import create_app, set_agent_state, get_agent_state
from probablyprofit.web.server import run_server_with_agent

__all__ = [
    "create_app",
    "set_agent_state",
    "get_agent_state",
    "run_server_with_agent",
]
