"""
Pytest configuration and shared fixtures.
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List

from probablyprofit.api.client import PolymarketClient, Market, Order, Position
from probablyprofit.risk.manager import RiskManager, RiskLimits
from probablyprofit.agent.base import BaseAgent, Observation, Decision


# =============================================================================
# ASYNC FIXTURES
# =============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# =============================================================================
# MOCK DATA FACTORIES
# =============================================================================

def create_mock_market(
    condition_id: str = "0x123abc",
    question: str = "Will it happen?",
    yes_price: float = 0.5,
    volume: float = 10000.0,
    liquidity: float = 5000.0,
    days_until_end: int = 7,
) -> Market:
    """Factory to create mock Market objects."""
    return Market(
        condition_id=condition_id,
        question=question,
        description=f"Test market: {question}",
        end_date=datetime.now() + timedelta(days=days_until_end),
        outcomes=["Yes", "No"],
        outcome_prices=[yes_price, 1.0 - yes_price],
        volume=volume,
        liquidity=liquidity,
        active=True,
        metadata={
            "clobTokenIds": ["token_yes_123", "token_no_456"]
        }
    )


def create_mock_position(
    market_id: str = "0x123abc",
    outcome: str = "Yes",
    size: float = 100.0,
    avg_price: float = 0.5,
    current_price: float = 0.6,
) -> Position:
    """Factory to create mock Position objects."""
    return Position(
        market_id=market_id,
        outcome=outcome,
        size=size,
        avg_price=avg_price,
        current_price=current_price,
        pnl=size * (current_price - avg_price)
    )


def create_mock_order(
    order_id: str = "order_123",
    market_id: str = "0x123abc",
    outcome: str = "Yes",
    side: str = "BUY",
    size: float = 10.0,
    price: float = 0.5,
    status: str = "filled",
) -> Order:
    """Factory to create mock Order objects."""
    return Order(
        order_id=order_id,
        market_id=market_id,
        outcome=outcome,
        side=side,
        size=size,
        price=price,
        status=status,
        filled_size=size if status == "filled" else 0.0,
        timestamp=datetime.now()
    )


# =============================================================================
# CLIENT FIXTURES
# =============================================================================

@pytest.fixture
def mock_client() -> AsyncMock:
    """Create a mock Polymarket client with default behavior."""
    client = AsyncMock(spec=PolymarketClient)

    # Default return values
    client.get_markets.return_value = [
        create_mock_market("0x001", "Will Bitcoin hit $100k?", 0.35, 50000),
        create_mock_market("0x002", "Will Trump win 2024?", 0.52, 100000),
        create_mock_market("0x003", "Will it rain tomorrow?", 0.70, 1000),
    ]
    client.get_positions.return_value = []
    client.get_balance.return_value = 1000.0
    client.place_order.return_value = create_mock_order()
    client.cancel_order.return_value = True
    client.get_market.return_value = create_mock_market()
    client.close.return_value = None

    return client


@pytest.fixture
def mock_client_with_positions(mock_client: AsyncMock) -> AsyncMock:
    """Client with existing positions."""
    mock_client.get_positions.return_value = [
        create_mock_position("0x001", "Yes", 50.0, 0.30, 0.35),
        create_mock_position("0x002", "No", 25.0, 0.45, 0.48),
    ]
    return mock_client


# =============================================================================
# RISK MANAGER FIXTURES
# =============================================================================

@pytest.fixture
def risk_manager() -> RiskManager:
    """Create a RiskManager with default settings."""
    return RiskManager(initial_capital=1000.0)


@pytest.fixture
def conservative_risk_manager() -> RiskManager:
    """Create a conservative RiskManager with tight limits."""
    limits = RiskLimits(
        max_position_size=50.0,
        max_total_exposure=200.0,
        max_positions=3,
        max_daily_loss=50.0,
        position_size_pct=0.02,
    )
    return RiskManager(limits=limits, initial_capital=1000.0)


@pytest.fixture
def aggressive_risk_manager() -> RiskManager:
    """Create an aggressive RiskManager with loose limits."""
    limits = RiskLimits(
        max_position_size=500.0,
        max_total_exposure=5000.0,
        max_positions=20,
        max_daily_loss=500.0,
        position_size_pct=0.10,
    )
    return RiskManager(limits=limits, initial_capital=5000.0)


# =============================================================================
# OBSERVATION FIXTURES
# =============================================================================

@pytest.fixture
def sample_observation(mock_client: AsyncMock) -> Observation:
    """Create a sample Observation."""
    return Observation(
        timestamp=datetime.now(),
        markets=mock_client.get_markets.return_value,
        positions=[],
        balance=1000.0,
        signals={},
        metadata={},
    )


@pytest.fixture
def observation_with_positions() -> Observation:
    """Create an Observation with existing positions."""
    return Observation(
        timestamp=datetime.now(),
        markets=[
            create_mock_market("0x001", "Test market 1", 0.45),
            create_mock_market("0x002", "Test market 2", 0.65),
        ],
        positions=[
            create_mock_position("0x001", "Yes", 100, 0.40, 0.45),
        ],
        balance=500.0,
        signals={"momentum": 0.7},
        metadata={"source": "test"},
    )


# =============================================================================
# AGENT FIXTURES
# =============================================================================

class MockAgent(BaseAgent):
    """Concrete implementation of BaseAgent for testing."""

    def __init__(self, *args, decision_to_return: Decision = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.decision_to_return = decision_to_return or Decision(
            action="hold",
            reasoning="Test hold decision",
            confidence=0.5
        )

    async def decide(self, observation: Observation) -> Decision:
        return self.decision_to_return


@pytest.fixture
def mock_agent(mock_client: AsyncMock, risk_manager: RiskManager) -> MockAgent:
    """Create a MockAgent for testing."""
    return MockAgent(
        client=mock_client,
        risk_manager=risk_manager,
        name="TestAgent",
        loop_interval=1,
        dry_run=True,
        enable_persistence=False,
    )


# =============================================================================
# API EXCEPTION FIXTURES
# =============================================================================

@pytest.fixture
def rate_limit_error():
    """Create a rate limit exception."""
    from probablyprofit.api.exceptions import RateLimitException
    return RateLimitException("Rate limit exceeded: 429")


@pytest.fixture
def network_error():
    """Create a network exception."""
    from probablyprofit.api.exceptions import NetworkException
    return NetworkException("Connection timeout")
