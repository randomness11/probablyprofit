"""
probablyprofit - AI-Powered Polymarket Trading Framework

A modular framework for building AI-powered trading bots for Polymarket.
Write your strategy in English. Let AI do the rest. Probably profit.
"""

__version__ = "0.1.0"

# Lazy imports to avoid loading heavy modules until needed
# This keeps CLI startup fast and prevents debug log spam


def __getattr__(name):
    """Lazy import handler for package attributes."""
    if name == "PolymarketClient":
        from probablyprofit.api.client import PolymarketClient
        return PolymarketClient
    elif name == "BaseAgent":
        from probablyprofit.agent.base import BaseAgent
        return BaseAgent
    elif name == "AnthropicAgent":
        from probablyprofit.agent.anthropic_agent import AnthropicAgent
        return AnthropicAgent
    elif name == "RiskManager":
        from probablyprofit.risk.manager import RiskManager
        return RiskManager
    elif name == "BacktestEngine":
        from probablyprofit.backtesting.engine import BacktestEngine
        return BacktestEngine
    elif name == "GeminiAgent":
        try:
            from probablyprofit.agent.gemini_agent import GeminiAgent
            return GeminiAgent
        except ImportError:
            return None
    elif name == "OpenAIAgent":
        try:
            from probablyprofit.agent.openai_agent import OpenAIAgent
            return OpenAIAgent
        except ImportError:
            return None
    raise AttributeError(f"module 'probablyprofit' has no attribute '{name}'")


__all__ = [
    "PolymarketClient",
    "BaseAgent",
    "AnthropicAgent",
    "RiskManager",
    "BacktestEngine",
    "GeminiAgent",
    "OpenAIAgent",
]

# Load environment variables (this is lightweight)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
