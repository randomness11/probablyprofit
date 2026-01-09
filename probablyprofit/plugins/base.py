"""
Base Plugin Classes

Abstract base classes for different plugin types.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass


@dataclass
class PluginConfig:
    """Configuration passed to plugins."""
    enabled: bool = True
    priority: int = 0  # Higher = runs first
    options: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.options is None:
            self.options = {}


class BasePlugin(ABC):
    """Base class for all plugins."""
    
    name: str = "base_plugin"
    version: str = "1.0.0"
    
    def __init__(self, config: PluginConfig = None):
        self.config = config or PluginConfig()
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize plugin resources. Override for custom setup."""
        self._initialized = True
    
    async def cleanup(self) -> None:
        """Clean up plugin resources. Override for custom teardown."""
        self._initialized = False
    
    @property
    def is_initialized(self) -> bool:
        return self._initialized


class DataSourcePlugin(BasePlugin):
    """
    Plugin for adding custom data sources.
    
    Example: Twitter sentiment, on-chain data, custom APIs.
    """
    
    @abstractmethod
    async def fetch(self, query: str) -> Dict[str, Any]:
        """
        Fetch data from the source.
        
        Args:
            query: Query string (e.g., market ID, keyword)
            
        Returns:
            Dictionary with fetched data
        """
        pass
    
    async def fetch_batch(self, queries: List[str]) -> List[Dict[str, Any]]:
        """Fetch multiple queries. Override for optimized batch fetching."""
        return [await self.fetch(q) for q in queries]


class AgentPlugin(BasePlugin):
    """
    Plugin for custom AI agents.
    
    Example: Custom LLM integration, rule-based agent.
    """
    
    @abstractmethod
    async def decide(self, observation: Any) -> Any:
        """
        Make a trading decision.
        
        Args:
            observation: Current market observation
            
        Returns:
            Decision object
        """
        pass


class StrategyPlugin(BasePlugin):
    """
    Plugin for trading strategies.
    
    Example: Custom entry/exit rules, signal generators.
    """
    
    @abstractmethod
    def get_prompt(self) -> str:
        """Return strategy prompt for AI agents."""
        pass
    
    @abstractmethod
    def filter_markets(self, markets: List[Any]) -> List[Any]:
        """Filter markets based on strategy criteria."""
        pass
    
    def score_market(self, market: Any) -> float:
        """Score a market (0-1). Override for custom scoring."""
        return 0.5


class RiskPlugin(BasePlugin):
    """
    Plugin for custom risk rules.
    
    Example: Custom position limits, correlation checks.
    """
    
    @abstractmethod
    def check(self, decision: Any, context: Dict[str, Any]) -> bool:
        """
        Check if a decision passes risk rules.
        
        Args:
            decision: Proposed trading decision
            context: Current portfolio/market context
            
        Returns:
            True if decision is allowed, False to block
        """
        pass
    
    def modify(self, decision: Any, context: Dict[str, Any]) -> Any:
        """Optionally modify a decision. Override for position sizing etc."""
        return decision


class OutputPlugin(BasePlugin):
    """
    Plugin for custom output handlers.
    
    Example: Slack notifications, custom logging, webhooks.
    """
    
    @abstractmethod
    async def send(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        Send output for an event.
        
        Args:
            event_type: Type of event (trade, error, alert)
            data: Event data
        """
        pass
