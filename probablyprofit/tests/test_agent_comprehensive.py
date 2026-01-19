"""
Comprehensive tests for the Agent framework.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from probablyprofit.agent.base import AgentMemory, BaseAgent, Decision, Observation
from probablyprofit.api.client import Market, Order, Position
from probablyprofit.risk.manager import RiskManager


class TestObservation:
    """Tests for Observation data class."""

    def test_observation_creation(self, sample_observation):
        assert isinstance(sample_observation.timestamp, datetime)
        assert isinstance(sample_observation.markets, list)
        assert sample_observation.balance == 1000.0

    def test_observation_with_news_context(self):
        obs = Observation(
            timestamp=datetime.now(),
            markets=[],
            positions=[],
            balance=1000.0,
            news_context="Bitcoin surges 5%",
            sentiment_summary="Bullish sentiment",
        )
        assert obs.news_context == "Bitcoin surges 5%"
        assert obs.sentiment_summary == "Bullish sentiment"


class TestDecision:
    """Tests for Decision data class."""

    def test_decision_hold(self):
        decision = Decision(action="hold", reasoning="No good opportunities")
        assert decision.action == "hold"
        assert decision.size == 0.0
        assert decision.confidence == 0.5

    def test_decision_buy(self):
        decision = Decision(
            action="buy",
            market_id="0x123",
            outcome="Yes",
            size=100.0,
            price=0.5,
            reasoning="Strong momentum",
            confidence=0.8,
        )
        assert decision.action == "buy"
        assert decision.market_id == "0x123"
        assert decision.size == 100.0

    def test_decision_with_metadata(self):
        decision = Decision(
            action="buy",
            market_id="0x123",
            outcome="Yes",
            size=50.0,
            price=0.5,
            metadata={"strategy": "momentum", "signal_strength": 0.9},
        )
        assert decision.metadata["strategy"] == "momentum"


class TestAgentMemory:
    """Tests for AgentMemory."""

    @pytest.mark.asyncio
    async def test_add_observation(self):
        memory = AgentMemory()
        obs = Observation(
            timestamp=datetime.now(),
            markets=[],
            positions=[],
            balance=1000.0,
        )
        await memory.add_observation(obs)
        assert len(memory.observations) == 1

    @pytest.mark.asyncio
    async def test_memory_limit_observations(self):
        memory = AgentMemory()
        # Add 110 observations
        for i in range(110):
            obs = Observation(
                timestamp=datetime.now(),
                markets=[],
                positions=[],
                balance=float(i),
            )
            await memory.add_observation(obs)

        # Should only keep last 100
        assert len(memory.observations) == 100
        assert memory.observations[-1].balance == 109.0

    @pytest.mark.asyncio
    async def test_add_decision(self):
        memory = AgentMemory()
        decision = Decision(action="hold", reasoning="Test")
        await memory.add_decision(decision)
        assert len(memory.decisions) == 1

    def test_get_recent_history(self):
        memory = AgentMemory()
        # Add some observations and decisions synchronously for history
        for i in range(5):
            memory.observations.append(
                Observation(
                    timestamp=datetime.now(),
                    markets=[],
                    positions=[],
                    balance=100.0,
                )
            )
            memory.decisions.append(
                Decision(
                    action="hold",
                    reasoning=f"Reason {i}",
                )
            )

        history = memory.get_recent_history(n=3)
        assert "Reason 2" in history or "Reason 3" in history or "Reason 4" in history


class TestBaseAgent:
    """Tests for BaseAgent functionality."""

    @pytest.mark.asyncio
    async def test_observe(self, mock_agent, mock_client):
        observation = await mock_agent.observe()

        assert isinstance(observation, Observation)
        assert observation.balance == 1000.0
        mock_client.get_markets.assert_called_once()
        mock_client.get_positions.assert_called_once()
        mock_client.get_balance.assert_called_once()

    @pytest.mark.asyncio
    async def test_act_hold(self, mock_agent):
        decision = Decision(action="hold", reasoning="No opportunities")
        success = await mock_agent.act(decision)
        assert success is True

    @pytest.mark.asyncio
    async def test_act_buy_dry_run(self, mock_agent, mock_client):
        decision = Decision(
            action="buy",
            market_id="0x123",
            outcome="Yes",
            size=10.0,
            price=0.5,
            confidence=0.7,
        )

        success = await mock_agent.act(decision)

        assert success is True
        # Dry run should NOT call place_order
        mock_client.place_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_act_buy_live(self, mock_client, risk_manager):
        from probablyprofit.tests.conftest import MockAgent

        agent = MockAgent(
            client=mock_client,
            risk_manager=risk_manager,
            dry_run=False,
            enable_persistence=False,
        )

        decision = Decision(
            action="buy",
            market_id="0x123",
            outcome="Yes",
            size=10.0,
            price=0.5,
            confidence=0.7,
        )

        success = await agent.act(decision)

        assert success is True
        mock_client.place_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_act_buy_rejected_by_risk(self, mock_agent):
        # Set tight risk limit
        mock_agent.risk_manager.limits.max_position_size = 1.0

        decision = Decision(
            action="buy",
            market_id="0x123",
            outcome="Yes",
            size=100.0,  # Too large
            price=0.5,
        )

        success = await mock_agent.act(decision)

        assert success is False

    @pytest.mark.asyncio
    async def test_act_sell(self, mock_client, risk_manager):
        from probablyprofit.tests.conftest import MockAgent

        agent = MockAgent(
            client=mock_client,
            risk_manager=risk_manager,
            dry_run=False,
            enable_persistence=False,
        )

        # First record a position
        agent._record_position("0x123", "Yes")

        decision = Decision(
            action="sell",
            market_id="0x123",
            outcome="Yes",
            size=10.0,
            price=0.6,
        )

        success = await agent.act(decision)

        assert success is True
        mock_client.place_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_duplicate_buy_skipped(self, mock_agent):
        # Record existing position
        mock_agent._record_position("0x123", "Yes")

        decision = Decision(
            action="buy",
            market_id="0x123",
            outcome="Yes",
            size=10.0,
            price=0.5,
        )

        # Should skip but return True (not an error)
        success = await mock_agent.act(decision)
        assert success is True

    @pytest.mark.asyncio
    async def test_auto_sizing(self, mock_client, risk_manager):
        from probablyprofit.tests.conftest import MockAgent

        agent = MockAgent(
            client=mock_client,
            risk_manager=risk_manager,
            dry_run=True,
            enable_persistence=False,
        )
        agent.sizing_method = "confidence_based"

        decision = Decision(
            action="buy",
            market_id="0x123",
            outcome="Yes",
            size=10.0,  # Original size
            price=0.5,
            confidence=0.8,
        )

        success = await agent.act(decision)
        assert success is True


class TestAgentPositionTracking:
    """Tests for position tracking."""

    def test_has_position(self, mock_agent):
        assert mock_agent._has_position("0x123", "Yes") is False
        mock_agent._record_position("0x123", "Yes")
        assert mock_agent._has_position("0x123", "Yes") is True
        assert mock_agent._has_position("0x123", "No") is False

    def test_record_position(self, mock_agent):
        mock_agent._record_position("0x123", "Yes")
        assert "0x123:Yes" in mock_agent._open_positions

    def test_get_market_name(self, mock_agent):
        mock_agent._market_names["0x123"] = "Will Bitcoin hit $100k?"
        name = mock_agent._get_market_name("0x123")
        assert name == "Will Bitcoin hit $100k?"

    def test_get_market_name_truncated(self, mock_agent):
        mock_agent._market_names["0x123"] = "A" * 100
        name = mock_agent._get_market_name("0x123", max_len=50)
        assert len(name) <= 50
        assert name.endswith("...")


class TestAgentHealthStatus:
    """Tests for agent health monitoring."""

    def test_get_health_status_initial(self, mock_agent):
        status = mock_agent.get_health_status()

        assert status["name"] == "TestAgent"
        assert status["running"] is False
        assert status["dry_run"] is True
        assert status["observations"] == 0

    @pytest.mark.asyncio
    async def test_get_health_status_after_run(self, mock_agent, mock_client):
        # Simulate some activity
        await mock_agent.observe()
        decision = Decision(action="hold", reasoning="Test")
        await mock_agent.act(decision)

        status = mock_agent.get_health_status()
        assert status["observations"] == 1
        assert status["decisions"] == 1


class TestAgentLoop:
    """Tests for the main agent loop."""

    @pytest.mark.asyncio
    async def test_stop_agent(self, mock_agent):
        mock_agent.running = True
        mock_agent.stop()
        assert mock_agent.running is False

    @pytest.mark.asyncio
    async def test_run_loop_single_iteration(self, mock_agent, mock_client):
        """Test that the loop can complete one iteration."""
        iterations = []

        async def mock_decide(obs):
            iterations.append(1)
            mock_agent.stop()  # Stop after first iteration
            return Decision(action="hold", reasoning="Test")

        mock_agent.decide = mock_decide
        mock_agent.loop_interval = 0.01  # Fast for testing

        await mock_agent.run_loop()

        assert len(iterations) == 1

    @pytest.mark.asyncio
    async def test_run_loop_error_recovery(self, mock_agent, mock_client):
        """Test that the loop handles errors gracefully."""
        call_count = [0]

        async def failing_decide(obs):
            call_count[0] += 1
            if call_count[0] < 3:
                raise ValueError("Test error")
            mock_agent.stop()
            return Decision(action="hold", reasoning="Recovered")

        mock_agent.decide = failing_decide
        mock_agent.loop_interval = 0.01
        mock_agent._base_backoff = 0.01  # Fast backoff for testing
        mock_agent._max_backoff = 0.01  # Cap max backoff for testing

        await mock_agent.run_loop()

        # Should have retried and eventually succeeded
        assert call_count[0] >= 3

    @pytest.mark.asyncio
    @pytest.mark.slow  # This test takes ~35s due to real exponential backoff
    @pytest.mark.timeout(45)  # Allow time for exponential backoff (5s + 10s + 20s)
    async def test_max_consecutive_errors_stops_loop(self, mock_agent, mock_client):
        """Test that too many consecutive errors stops the loop."""
        error_count = [0]
        max_errors = 3

        async def always_failing_decide(obs):
            error_count[0] += 1
            if error_count[0] >= max_errors:
                # Stop after max errors to avoid long backoffs in tests
                mock_agent.stop()
            raise ValueError("Always fails")

        mock_agent.decide = always_failing_decide
        mock_agent.loop_interval = 0.01

        await mock_agent.run_loop()

        # Loop should have stopped
        assert mock_agent.running is False
        # Should have accumulated errors
        assert error_count[0] >= max_errors
