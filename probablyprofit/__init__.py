"""
probablyprofit - AI-Powered Polymarket Trading Framework

A modular framework for building AI-powered trading bots for Polymarket.
Inspired by a16z's approach to crypto innovation.
"""

__version__ = "0.1.0"

from probablyprofit.api.client import PolymarketClient
from probablyprofit.agent.base import BaseAgent
from probablyprofit.agent.anthropic_agent import AnthropicAgent
from probablyprofit.risk.manager import RiskManager
from probablyprofit.backtesting.engine import BacktestEngine

# Optional AI providers
try:
    from probablyprofit.agent.gemini_agent import GeminiAgent
except ImportError:
    GeminiAgent = None

try:
    from probablyprofit.agent.openai_agent import OpenAIAgent
except ImportError:
    OpenAIAgent = None

__all__ = [
    "PolymarketClient",
    "BaseAgent",
    "AnthropicAgent",
    "RiskManager",
    "BacktestEngine",
    "GeminiAgent",
    "OpenAIAgent",
]

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
