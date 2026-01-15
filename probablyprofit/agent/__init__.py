"""AI Agent framework."""

from probablyprofit.agent.anthropic_agent import AnthropicAgent
from probablyprofit.agent.base import BaseAgent
from probablyprofit.agent.ensemble import EnsembleAgent, VotingStrategy
from probablyprofit.agent.fallback import FallbackAgent, FallbackConfig, create_fallback_agent

# Optional AI providers
try:
    from probablyprofit.agent.gemini_agent import GeminiAgent
except ImportError:
    GeminiAgent = None

try:
    from probablyprofit.agent.openai_agent import OpenAIAgent
except ImportError:
    OpenAIAgent = None

try:
    from probablyprofit.agent.mock_agent import MockAgent
except ImportError:
    MockAgent = None

__all__ = [
    "BaseAgent",
    "AnthropicAgent",
    "GeminiAgent",
    "OpenAIAgent",
    "EnsembleAgent",
    "VotingStrategy",
    "MockAgent",
    # Fallback
    "FallbackAgent",
    "create_fallback_agent",
    "FallbackConfig",
]
