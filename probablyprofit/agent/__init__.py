"""AI Agent framework."""

from probablyprofit.agent.base import BaseAgent
from probablyprofit.agent.anthropic_agent import AnthropicAgent
from probablyprofit.agent.ensemble import EnsembleAgent, VotingStrategy

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

__all__ = ["BaseAgent", "AnthropicAgent", "GeminiAgent", "OpenAIAgent", "EnsembleAgent", "VotingStrategy", "MockAgent"]

