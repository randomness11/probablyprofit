import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from probablyprofit.agent.base import BaseAgent, Observation, Decision
from probablyprofit.risk.manager import RiskManager

class MockAgent(BaseAgent):
    async def decide(self, observation):
        return Decision(
            action="buy",
            market_id="test_market",
            outcome="Yes",
            size=10.0,
            price=0.5
        )

@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.get_markets.return_value = []
    client.get_positions.return_value = []
    client.get_balance.return_value = 1000.0
    client.place_order.return_value = MagicMock(size=10.0, price=0.5)
    return client

@pytest.fixture
def risk_manager():
    return RiskManager(initial_capital=1000.0)

@pytest.mark.asyncio
async def test_agent_observe(mock_client, risk_manager):
    agent = MockAgent(mock_client, risk_manager, loop_interval=1)
    obs = await agent.observe()
    
    assert isinstance(obs, Observation)
    assert obs.balance == 1000.0
    mock_client.get_markets.assert_called_once()
    mock_client.get_positions.assert_called_once()

@pytest.mark.asyncio
async def test_agent_act_success(mock_client, risk_manager):
    agent = MockAgent(mock_client, risk_manager)
    decision = Decision(action="buy", market_id="m1", outcome="Yes", size=10, price=0.5)
    
    success = await agent.act(decision)
    
    assert success is True
    mock_client.place_order.assert_called_once()
    # Check if trade was recorded in risk manager
    assert len(risk_manager.trades) == 1

@pytest.mark.asyncio
async def test_agent_act_risk_rejection(mock_client, risk_manager):
    # Set insane risk limit to force rejection
    risk_manager.limits.max_position_size = 1.0 
    
    agent = MockAgent(mock_client, risk_manager)
    decision = Decision(action="buy", market_id="m1", outcome="Yes", size=100, price=0.5)
    
    success = await agent.act(decision)
    
    assert success is False
    mock_client.place_order.assert_not_called()
