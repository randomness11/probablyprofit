"""
Platform Abstraction Layer

Provides a unified interface for different prediction market platforms.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class UnifiedMarket(BaseModel):
    """Unified market representation across platforms."""

    id: str  # ticker or condition_id
    question: str
    description: Optional[str] = None
    end_date: Any  # datetime
    outcomes: List[str]
    outcome_prices: List[float]
    volume: float
    liquidity: float
    active: bool = True
    platform: str = "unknown"
    metadata: Dict[str, Any] = {}


class UnifiedOrder(BaseModel):
    """Unified order representation."""

    order_id: Optional[str] = None
    market_id: str
    outcome: str
    side: str  # buy/sell
    size: float
    price: float
    status: str = "pending"
    platform: str = "unknown"
    metadata: Dict[str, Any] = {}


class UnifiedPosition(BaseModel):
    """Unified position representation."""

    market_id: str
    outcome: str
    size: float
    avg_price: float
    current_price: float
    pnl: float = 0.0
    platform: str = "unknown"

    @property
    def value(self) -> float:
        return self.size * self.current_price

    @property
    def unrealized_pnl(self) -> float:
        return self.size * (self.current_price - self.avg_price)


class PlatformClient(ABC):
    """Abstract base class for all platform clients."""

    @abstractmethod
    async def get_markets(self, **kwargs) -> List[Any]:
        """Get active markets."""
        pass

    @abstractmethod
    async def get_market(self, market_id: str) -> Optional[Any]:
        """Get specific market."""
        pass

    @abstractmethod
    async def place_order(self, **kwargs) -> Optional[Any]:
        """Place an order."""
        pass

    @abstractmethod
    async def get_positions(self) -> List[Any]:
        """Get current positions."""
        pass

    @abstractmethod
    async def get_balance(self) -> float:
        """Get account balance in USD."""
        pass

    @abstractmethod
    async def close(self):
        """Close connections."""
        pass

    @abstractmethod
    def to_unified_market(self, market: Any) -> UnifiedMarket:
        """Convert platform-specific market to unified format."""
        pass


def create_platform_client(platform: str, **kwargs) -> PlatformClient:
    """
    Factory function to create platform clients.

    Args:
        platform: "polymarket"
        **kwargs: Platform-specific configuration

    Returns:
        Platform client instance
    """
    if platform.lower() == "polymarket":
        from probablyprofit.api.client import PolymarketClient

        return PolymarketClient(
            private_key=kwargs.get("private_key"),
            chain_id=kwargs.get("chain_id", 137),
            testnet=kwargs.get("testnet", False),
        )

    else:
        raise ValueError(f"Unknown platform: {platform}. Supported: polymarket")
