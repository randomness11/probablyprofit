"""
Integration Tests for Production Hardening

Tests end-to-end flows with mock exchange:
- Full trade flow
- Partial fill handling
- Kill switch
- Risk management
- Crash recovery
"""

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

# Set test environment
os.environ["TESTING"] = "true"


class TestKillSwitch:
    """Tests for the kill switch system."""

    def test_kill_switch_activation(self):
        """Test that kill switch can be activated."""
        from probablyprofit.utils.killswitch import (
            KillSwitch,
            KillSwitchError,
        )

        # Use temp file for testing
        with tempfile.NamedTemporaryFile(delete=False) as f:
            kill_file = Path(f.name)
        kill_file.unlink()  # Remove it first

        reason_file = Path(str(kill_file) + ".reason")

        try:
            ks = KillSwitch(kill_file=kill_file, reason_file=reason_file)

            # Initially not active
            assert not ks.is_active()

            # Activate
            ks.activate("Test activation")
            assert ks.is_active()
            assert "Test activation" in ks.get_reason()

            # Check raises
            with pytest.raises(KillSwitchError):
                ks.check_and_raise()

            # Deactivate
            ks.deactivate()
            assert not ks.is_active()

        finally:
            # Cleanup
            if kill_file.exists():
                kill_file.unlink()
            if reason_file.exists():
                reason_file.unlink()

    def test_kill_switch_file_persistence(self):
        """Test that kill switch persists via file."""
        from probablyprofit.utils.killswitch import KillSwitch

        with tempfile.NamedTemporaryFile(delete=False) as f:
            kill_file = Path(f.name)
        kill_file.unlink()
        reason_file = Path(str(kill_file) + ".reason")

        try:
            # Create and activate first instance
            ks1 = KillSwitch(kill_file=kill_file, reason_file=reason_file)
            ks1.activate("Persistent test")

            # Create second instance - should see kill switch
            ks2 = KillSwitch(kill_file=kill_file, reason_file=reason_file)
            assert ks2.is_active()

            # Deactivate via second instance
            ks2.deactivate()

            # First instance should see deactivation
            assert not ks1.is_active()

        finally:
            if kill_file.exists():
                kill_file.unlink()
            if reason_file.exists():
                reason_file.unlink()


class TestRiskManagerDrawdown:
    """Tests for risk manager drawdown tracking."""

    def test_drawdown_calculation(self):
        """Test drawdown is calculated correctly."""
        from probablyprofit.risk.manager import RiskManager, RiskLimits

        rm = RiskManager(initial_capital=1000.0)

        # Initial drawdown is 0
        assert rm.get_current_drawdown() == 0.0

        # Simulate loss
        rm.current_capital = 800.0
        assert rm.get_current_drawdown() == pytest.approx(0.2, rel=0.01)

        # Update peak (should not change since capital decreased)
        rm.update_peak_capital()
        assert rm.peak_capital == 1000.0

        # Recover
        rm.current_capital = 900.0
        assert rm.get_current_drawdown() == pytest.approx(0.1, rel=0.01)

        # New high
        rm.current_capital = 1200.0
        rm.update_peak_capital()
        assert rm.peak_capital == 1200.0

    def test_drawdown_halt(self):
        """Test trading halts when max drawdown exceeded."""
        from probablyprofit.risk.manager import RiskManager

        rm = RiskManager(initial_capital=1000.0)
        rm.max_drawdown_pct = 0.25  # 25% max drawdown

        # Under limit - can trade
        rm.current_capital = 800.0  # 20% down
        assert not rm.check_drawdown_limit()
        assert rm.can_open_position(10, 0.5)

        # Over limit - cannot trade
        rm.current_capital = 700.0  # 30% down
        assert rm.check_drawdown_limit()
        assert not rm.can_open_position(10, 0.5)

    def test_exposure_recalculation(self):
        """Test that exposure is correctly recalculated from positions."""
        from probablyprofit.risk.manager import RiskManager

        rm = RiskManager(initial_capital=1000.0)

        # Add positions
        rm.update_position("market1", 100, price=0.5)  # $50 exposure
        rm.update_position("market2", 200, price=0.3)  # $60 exposure

        # Recalculate
        exposure = rm.recalculate_exposure()
        assert exposure == pytest.approx(110, rel=0.01)

        # Close one position
        rm.update_position("market1", 0)
        exposure = rm.recalculate_exposure()
        assert exposure == pytest.approx(60, rel=0.01)


class TestOrderManagerPartialFills:
    """Tests for order manager partial fill handling."""

    @pytest.mark.asyncio
    async def test_partial_fill_timeout(self):
        """Test that partial fills timeout and cancel."""
        from datetime import datetime, timedelta

        from probablyprofit.api.order_manager import (
            Fill,
            ManagedOrder,
            OrderBook,
            OrderManager,
            OrderSide,
            OrderStatus,
            OrderType,
        )

        om = OrderManager(client=None, partial_fill_timeout=1.0)  # 1 second timeout

        # Create partially filled order
        order = ManagedOrder(
            order_id="test_order_1",
            market_id="test_market",
            outcome="YES",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            size=100,
            price=0.5,
        )

        # Add a fill from 2 seconds ago
        old_fill = Fill(
            fill_id="fill_1",
            order_id="test_order_1",
            size=50,
            price=0.5,
            timestamp=datetime.now() - timedelta(seconds=2),
        )
        order.add_fill(old_fill)

        assert order.status == OrderStatus.PARTIALLY_FILLED

        # Add to order book
        await om.order_book.add(order)

        # Check for timeouts - should flag this order
        timed_out = await om.check_partial_fill_timeouts()

        # Order should be cancelled (in dry run mode without client)
        assert len(timed_out) == 1
        assert timed_out[0].order_id == "test_order_1"


class TestMockExchange:
    """Tests using the mock exchange."""

    @pytest.mark.asyncio
    async def test_instant_fill(self):
        """Test instant order fills."""
        from probablyprofit.tests.mock_exchange import (
            FillBehavior,
            MockExchangeClient,
        )

        client = MockExchangeClient(default_fill_behavior=FillBehavior.INSTANT)

        order = await client.place_order(
            market_id="test_market",
            outcome="YES",
            side="BUY",
            size=100,
            price=0.5,
        )

        assert order.status == "filled"
        assert order.filled_size == 100

    @pytest.mark.asyncio
    async def test_partial_fill(self):
        """Test partial order fills."""
        from probablyprofit.tests.mock_exchange import (
            FillBehavior,
            MockExchangeClient,
        )

        client = MockExchangeClient(
            default_fill_behavior=FillBehavior.PARTIAL,
            partial_fill_pct=0.5,
        )

        order = await client.place_order(
            market_id="test_market",
            outcome="YES",
            side="BUY",
            size=100,
            price=0.5,
        )

        assert order.status == "partial"
        assert order.filled_size == pytest.approx(50, rel=0.01)

    @pytest.mark.asyncio
    async def test_order_rejection(self):
        """Test order rejection handling."""
        from probablyprofit.tests.mock_exchange import (
            FillBehavior,
            MockExchangeClient,
        )

        client = MockExchangeClient(default_fill_behavior=FillBehavior.REJECT)

        with pytest.raises(Exception, match="rejected"):
            await client.place_order(
                market_id="test_market",
                outcome="YES",
                side="BUY",
                size=100,
                price=0.5,
            )

    @pytest.mark.asyncio
    async def test_position_tracking(self):
        """Test position tracking after fills."""
        from probablyprofit.tests.mock_exchange import (
            FillBehavior,
            MockExchangeClient,
        )

        client = MockExchangeClient(default_fill_behavior=FillBehavior.INSTANT)

        # Buy
        await client.place_order(
            market_id="test_market",
            outcome="YES",
            side="BUY",
            size=100,
            price=0.5,
        )

        positions = await client.get_positions()
        assert len(positions) == 1
        assert positions[0].size == 100
        assert positions[0].avg_price == 0.5

        # Buy more at different price
        await client.place_order(
            market_id="test_market",
            outcome="YES",
            side="BUY",
            size=100,
            price=0.6,
        )

        positions = await client.get_positions()
        assert positions[0].size == 200
        assert positions[0].avg_price == pytest.approx(0.55, rel=0.01)


class TestCredentialValidation:
    """Tests for credential validation."""

    def test_placeholder_detection(self):
        """Test detection of placeholder values."""
        from probablyprofit.config import is_placeholder_value

        # Placeholders
        assert is_placeholder_value("your_api_key")
        assert is_placeholder_value("sk-your_openai_key")
        assert is_placeholder_value("your_private_key_here")
        assert is_placeholder_value("example_key")
        assert is_placeholder_value("test_api_key")

        # Real values (should not be detected)
        assert not is_placeholder_value("sk-1234567890abcdef")
        assert not is_placeholder_value("sk-ant-api03-something")

    def test_test_private_key_detection(self):
        """Test detection of the test private key."""
        from probablyprofit.config import is_test_private_key

        test_key = "0x1111111111111111111111111111111111111111111111111111111111111111"

        assert is_test_private_key(test_key)
        assert is_test_private_key(test_key.lower())
        assert is_test_private_key(test_key[2:])  # Without 0x prefix

        # Real key should not match
        assert not is_test_private_key(
            "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
        )


class TestTelegramAlerter:
    """Tests for Telegram alerting."""

    def test_rate_limiting(self):
        """Test rate limiting logic."""
        import time

        from probablyprofit.alerts.telegram import TelegramAlerter

        alerter = TelegramAlerter(rate_limit_per_minute=5)

        # Should be able to send initially
        assert alerter._can_send()

        # Simulate sending 5 messages
        for _ in range(5):
            alerter._record_send()

        # Should be rate limited now
        assert not alerter._can_send()

        # Wait for rate limit window to pass (simulate)
        alerter._message_times.clear()
        assert alerter._can_send()

    def test_message_formatting(self):
        """Test alert message formatting."""
        from probablyprofit.alerts.telegram import Alert, AlertLevel, TelegramAlerter
        from datetime import datetime

        alerter = TelegramAlerter()

        alert = Alert(
            level=AlertLevel.WARNING,
            title="Test Alert",
            message="This is a test",
            timestamp=datetime.now(),
            metadata={"key": "value", "number": 123.456},
        )

        formatted = alerter._format_message(alert)

        assert "WARNING" in formatted
        assert "Test Alert" in formatted
        assert "This is a test" in formatted
        assert "key" in formatted
        assert "123.4" in formatted  # Formatted number


# Run tests with: pytest probablyprofit/tests/test_integration.py -v
