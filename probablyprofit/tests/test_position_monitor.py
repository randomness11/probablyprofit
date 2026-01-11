"""
Tests for Position Monitor.
"""
import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from probablyprofit.trading.position_monitor import (
    PositionMonitor,
    PositionAlert,
    MonitoredPosition,
)
from probablyprofit.api.client import Position
from probablyprofit.risk.manager import RiskManager


@pytest.fixture
def mock_client():
    """Create a mock Polymarket client."""
    client = AsyncMock()
    client.get_positions.return_value = []
    client.get_market.return_value = MagicMock(
        outcomes=["Yes", "No"],
        outcome_prices=[0.5, 0.5],
    )
    client.place_order.return_value = MagicMock(order_id="order_123")
    return client


@pytest.fixture
def risk_manager():
    return RiskManager(initial_capital=1000.0)


@pytest.fixture
def monitor(mock_client, risk_manager):
    return PositionMonitor(
        client=mock_client,
        risk_manager=risk_manager,
        check_interval=0.1,
        dry_run=True,
    )


class TestMonitoredPosition:
    """Tests for MonitoredPosition dataclass."""

    def test_creation(self):
        pos = MonitoredPosition(
            market_id="0x123",
            outcome="Yes",
            entry_price=0.5,
            size=100.0,
            stop_loss_price=0.4,
            take_profit_price=0.7,
        )
        assert pos.market_id == "0x123"
        assert pos.entry_price == 0.5
        assert pos.stop_loss_price == 0.4


class TestPositionMonitor:
    """Tests for PositionMonitor."""

    def test_add_position(self, monitor):
        pos_id = monitor.add_position(
            market_id="0x123",
            outcome="Yes",
            entry_price=0.5,
            size=100.0,
            stop_loss_pct=0.20,
            take_profit_pct=0.50,
        )

        assert pos_id == "0x123:Yes"
        assert pos_id in monitor.positions

        pos = monitor.positions[pos_id]
        assert pos.stop_loss_price == pytest.approx(0.4, rel=0.01)
        assert pos.take_profit_price == pytest.approx(0.75, rel=0.01)

    def test_add_position_explicit_prices(self, monitor):
        pos_id = monitor.add_position(
            market_id="0x123",
            outcome="Yes",
            entry_price=0.5,
            size=100.0,
            stop_loss_price=0.35,
            take_profit_price=0.80,
        )

        pos = monitor.positions[pos_id]
        assert pos.stop_loss_price == 0.35
        assert pos.take_profit_price == 0.80

    def test_remove_position(self, monitor):
        monitor.add_position(
            market_id="0x123",
            outcome="Yes",
            entry_price=0.5,
            size=100.0,
        )
        assert monitor.remove_position("0x123:Yes") is True
        assert "0x123:Yes" not in monitor.positions
        assert monitor.remove_position("nonexistent") is False

    def test_update_thresholds(self, monitor):
        monitor.add_position(
            market_id="0x123",
            outcome="Yes",
            entry_price=0.5,
            size=100.0,
        )

        assert monitor.update_thresholds(
            "0x123:Yes",
            stop_loss_price=0.30,
            take_profit_price=0.90,
        ) is True

        pos = monitor.positions["0x123:Yes"]
        assert pos.stop_loss_price == 0.30
        assert pos.take_profit_price == 0.90

    @pytest.mark.asyncio
    async def test_check_positions_stop_loss(self, monitor, mock_client):
        # Add position with stop-loss at 0.4
        monitor.add_position(
            market_id="0x123",
            outcome="Yes",
            entry_price=0.5,
            size=100.0,
            stop_loss_price=0.4,
        )

        # Mock current price below stop-loss
        mock_client.get_positions.return_value = [
            Position(
                market_id="0x123",
                outcome="Yes",
                size=100.0,
                avg_price=0.5,
                current_price=0.35,  # Below 0.4 stop-loss
            )
        ]

        alerts = await monitor.check_positions()

        assert len(alerts) == 1
        assert alerts[0].alert_type == "stop_loss"
        assert "0x123:Yes" not in monitor.positions  # Position should be removed

    @pytest.mark.asyncio
    async def test_check_positions_take_profit(self, monitor, mock_client):
        # Add position with take-profit at 0.75
        monitor.add_position(
            market_id="0x123",
            outcome="Yes",
            entry_price=0.5,
            size=100.0,
            take_profit_price=0.75,
        )

        # Mock current price above take-profit
        mock_client.get_positions.return_value = [
            Position(
                market_id="0x123",
                outcome="Yes",
                size=100.0,
                avg_price=0.5,
                current_price=0.80,  # Above 0.75 take-profit
            )
        ]

        alerts = await monitor.check_positions()

        assert len(alerts) == 1
        assert alerts[0].alert_type == "take_profit"
        assert alerts[0].metadata["pnl"] == pytest.approx(30.0, rel=0.01)

    @pytest.mark.asyncio
    async def test_check_positions_no_trigger(self, monitor, mock_client):
        monitor.add_position(
            market_id="0x123",
            outcome="Yes",
            entry_price=0.5,
            size=100.0,
            stop_loss_price=0.4,
            take_profit_price=0.75,
        )

        # Price between stop-loss and take-profit
        mock_client.get_positions.return_value = [
            Position(
                market_id="0x123",
                outcome="Yes",
                size=100.0,
                avg_price=0.5,
                current_price=0.55,
            )
        ]

        alerts = await monitor.check_positions()
        assert len(alerts) == 0
        assert "0x123:Yes" in monitor.positions

    @pytest.mark.asyncio
    async def test_trailing_stop(self, monitor, mock_client):
        monitor.add_position(
            market_id="0x123",
            outcome="Yes",
            entry_price=0.5,
            size=100.0,
            trailing_stop_pct=0.10,  # 10% trailing stop
        )

        pos = monitor.positions["0x123:Yes"]
        assert pos.highest_price == 0.5

        # Price goes up - trailing stop should move up
        mock_client.get_positions.return_value = [
            Position(
                market_id="0x123",
                outcome="Yes",
                size=100.0,
                avg_price=0.5,
                current_price=0.7,
            )
        ]

        await monitor.check_positions()

        # Highest price should update
        assert pos.highest_price == 0.7
        # Stop loss should be 10% below highest = 0.63
        assert pos.stop_loss_price == pytest.approx(0.63, rel=0.01)

    @pytest.mark.asyncio
    async def test_start_stop(self, monitor):
        await monitor.start()
        assert monitor._running is True

        await asyncio.sleep(0.2)  # Let it run a few iterations

        await monitor.stop()
        assert monitor._running is False

    def test_stats(self, monitor):
        monitor.add_position(
            market_id="0x123",
            outcome="Yes",
            entry_price=0.5,
            size=100.0,
        )

        stats = monitor.stats
        assert stats["positions_monitored"] == 1
        assert stats["dry_run"] is True

    def test_alert_callback(self, mock_client, risk_manager):
        alerts_received = []

        def on_alert(alert: PositionAlert):
            alerts_received.append(alert)

        monitor = PositionMonitor(
            client=mock_client,
            risk_manager=risk_manager,
            dry_run=True,
            on_alert=on_alert,
        )

        # The callback will be called when alerts are triggered
        assert monitor.on_alert == on_alert
