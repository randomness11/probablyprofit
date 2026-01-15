"""
Comprehensive tests for the Risk Manager.
"""

import pytest

from probablyprofit.risk.manager import RiskLimits, RiskManager


class TestRiskLimits:
    """Tests for RiskLimits configuration."""

    def test_default_limits(self):
        limits = RiskLimits()
        assert limits.max_position_size == 100.0
        assert limits.max_total_exposure == 1000.0
        assert limits.max_positions == 10
        assert limits.max_daily_loss == 200.0
        assert limits.position_size_pct == 0.05

    def test_custom_limits(self):
        limits = RiskLimits(
            max_position_size=50.0,
            max_total_exposure=500.0,
            max_positions=5,
        )
        assert limits.max_position_size == 50.0
        assert limits.max_total_exposure == 500.0
        assert limits.max_positions == 5


class TestRiskManagerInit:
    """Tests for RiskManager initialization."""

    def test_initialization_default(self):
        rm = RiskManager()
        assert rm.initial_capital == 1000.0
        assert rm.current_capital == 1000.0
        assert rm.current_exposure == 0.0
        assert rm.daily_pnl == 0.0
        assert len(rm.trades) == 0

    def test_initialization_custom_capital(self):
        rm = RiskManager(initial_capital=5000.0)
        assert rm.initial_capital == 5000.0
        assert rm.current_capital == 5000.0

    def test_initialization_custom_limits(self):
        limits = RiskLimits(max_position_size=200.0)
        rm = RiskManager(limits=limits)
        assert rm.limits.max_position_size == 200.0


class TestCanOpenPosition:
    """Tests for position opening validation."""

    def test_valid_position(self, risk_manager):
        assert risk_manager.can_open_position(size=50, price=0.5) is True

    def test_exceeds_position_size_limit(self, risk_manager):
        # Default max is 100, 300 * 0.5 = 150 > 100
        assert risk_manager.can_open_position(size=300, price=0.5) is False

    def test_exceeds_exposure_limit(self, risk_manager):
        # Simulate existing exposure
        risk_manager.current_exposure = 950.0
        # New position of 200*0.5=100 would bring total to 1050 > 1000 (default max)
        assert risk_manager.can_open_position(size=200, price=0.5) is False

    def test_exceeds_max_positions(self, risk_manager):
        # Fill up positions
        for i in range(10):
            risk_manager.open_positions[f"market_{i}"] = 10.0
        assert risk_manager.can_open_position(size=10, price=0.5) is False

    def test_daily_loss_limit_exceeded(self, risk_manager):
        risk_manager.daily_pnl = -250.0  # Exceeds 200 default
        assert risk_manager.can_open_position(size=10, price=0.5) is False

    def test_position_too_large_relative_to_capital(self, risk_manager):
        # Position > 50% of capital
        assert risk_manager.can_open_position(size=1500, price=0.5) is False

    def test_edge_case_exactly_at_limit(self, risk_manager):
        # Exactly at max position size limit
        # 200 * 0.5 = 100 = max_position_size
        assert risk_manager.can_open_position(size=200, price=0.5) is True


class TestKellySizing:
    """Tests for Kelly criterion position sizing."""

    def test_kelly_basic(self, risk_manager):
        # 60% win probability, price 0.5, default 0.25 fraction
        # Kelly = (0.6 - 0.4/1.0) * 0.25 = 0.2 * 0.25 = 0.05
        # Position = 1000 * 0.05 / 0.5 = 100
        size = risk_manager.kelly_size(win_prob=0.6, price=0.5, fraction=0.25)
        assert size == pytest.approx(100.0, rel=0.01)

    def test_kelly_high_confidence(self, risk_manager):
        # 80% confidence should give larger size
        size_high = risk_manager.kelly_size(win_prob=0.8, price=0.5, fraction=0.25)
        size_low = risk_manager.kelly_size(win_prob=0.6, price=0.5, fraction=0.25)
        assert size_high > size_low

    def test_kelly_edge_price(self, risk_manager):
        # Price at edge (0 or 1) should return 0
        assert risk_manager.kelly_size(win_prob=0.6, price=0.0) == 0.0
        assert risk_manager.kelly_size(win_prob=0.6, price=1.0) == 0.0

    def test_kelly_negative_edge(self, risk_manager):
        # When win_prob < price, Kelly is negative -> should return 0
        # 40% win prob at 0.5 price means negative edge
        size = risk_manager.kelly_size(win_prob=0.4, price=0.5, fraction=0.25)
        assert size >= 0.0  # Should not be negative


class TestPositionSizing:
    """Tests for various position sizing methods."""

    def test_fixed_pct_sizing(self, risk_manager):
        # 5% of 1000 = 50, at price 0.5 = 100 shares
        size = risk_manager.calculate_position_size(price=0.5, confidence=0.5, method="fixed_pct")
        assert size == pytest.approx(100.0, rel=0.01)

    def test_confidence_based_sizing(self, risk_manager):
        # Base 5% * 0.8 confidence = 4% of 1000 = 40, at price 0.5 = 80 shares
        size = risk_manager.calculate_position_size(
            price=0.5, confidence=0.8, method="confidence_based"
        )
        assert size == pytest.approx(80.0, rel=0.01)

    def test_kelly_sizing_via_method(self, risk_manager):
        risk_manager.limits.max_position_size = 1000.0  # Increase to test Kelly
        size = risk_manager.calculate_position_size(
            price=0.5, confidence=0.6, method="kelly", kelly_fraction=0.25
        )
        assert size == pytest.approx(100.0, rel=0.01)

    def test_dynamic_sizing_basic(self, risk_manager):
        size = risk_manager.calculate_position_size(price=0.5, confidence=0.7, method="dynamic")
        assert size > 0

    def test_sizing_respects_max_limit(self, risk_manager):
        # Even with high confidence, should not exceed max
        risk_manager.limits.max_position_size = 50.0
        size = risk_manager.calculate_position_size(
            price=0.5, confidence=1.0, method="confidence_based"
        )
        assert size <= 100.0  # 50 / 0.5 = 100 shares max

    def test_unknown_method_defaults(self, risk_manager):
        # Unknown method should default to fixed_pct
        size = risk_manager.calculate_position_size(
            price=0.5, confidence=0.5, method="unknown_method"
        )
        assert size == pytest.approx(100.0, rel=0.01)


class TestStopLossAndTakeProfit:
    """Tests for stop-loss and take-profit triggers."""

    def test_stop_loss_triggers(self, risk_manager):
        # 40% loss should trigger at 20% threshold
        assert risk_manager.should_stop_loss(entry_price=0.5, current_price=0.3, size=100) is True

    def test_stop_loss_not_triggered(self, risk_manager):
        # 10% loss should not trigger at 20% threshold
        assert risk_manager.should_stop_loss(entry_price=0.5, current_price=0.45, size=100) is False

    def test_stop_loss_custom_threshold(self, risk_manager):
        # 15% loss with 10% threshold should trigger
        assert (
            risk_manager.should_stop_loss(
                entry_price=0.5, current_price=0.425, size=100, stop_loss_pct=0.10
            )
            is True
        )

    def test_take_profit_triggers(self, risk_manager):
        # 60% profit should trigger at 50% threshold
        assert risk_manager.should_take_profit(entry_price=0.5, current_price=0.8, size=100) is True

    def test_take_profit_not_triggered(self, risk_manager):
        # 20% profit should not trigger at 50% threshold
        assert (
            risk_manager.should_take_profit(entry_price=0.5, current_price=0.6, size=100) is False
        )

    def test_take_profit_custom_threshold(self, risk_manager):
        # 30% profit with 25% threshold should trigger
        assert (
            risk_manager.should_take_profit(
                entry_price=0.5, current_price=0.65, size=100, take_profit_pct=0.25
            )
            is True
        )


class TestTradeRecording:
    """Tests for trade recording and tracking."""

    def test_record_trade(self, risk_manager):
        risk_manager.record_trade(size=100, price=0.5, pnl=10.0)

        assert len(risk_manager.trades) == 1
        assert risk_manager.trades[0].size == 100
        assert risk_manager.trades[0].price == 0.5
        assert risk_manager.trades[0].pnl == 10.0
        assert risk_manager.daily_pnl == 10.0
        assert risk_manager.current_capital == 1010.0

    def test_record_multiple_trades(self, risk_manager):
        risk_manager.record_trade(size=100, price=0.5, pnl=10.0)
        risk_manager.record_trade(size=50, price=0.6, pnl=-5.0)

        assert len(risk_manager.trades) == 2
        assert risk_manager.daily_pnl == 5.0
        assert risk_manager.current_capital == 1005.0

    def test_exposure_tracking(self, risk_manager):
        risk_manager.record_trade(size=100, price=0.5)
        assert risk_manager.current_exposure == 50.0  # 100 * 0.5


class TestPositionTracking:
    """Tests for open position tracking."""

    def test_update_position_open(self, risk_manager):
        risk_manager.update_position("market_1", 100.0)
        assert "market_1" in risk_manager.open_positions
        assert risk_manager.open_positions["market_1"] == 100.0

    def test_update_position_close(self, risk_manager):
        risk_manager.update_position("market_1", 100.0)
        risk_manager.update_position("market_1", 0)
        assert "market_1" not in risk_manager.open_positions

    def test_update_position_modify(self, risk_manager):
        risk_manager.update_position("market_1", 100.0)
        risk_manager.update_position("market_1", 150.0)
        assert risk_manager.open_positions["market_1"] == 150.0


class TestStats:
    """Tests for statistics gathering."""

    def test_get_stats_initial(self, risk_manager):
        stats = risk_manager.get_stats()
        assert stats["current_capital"] == 1000.0
        assert stats["total_pnl"] == 0.0
        assert stats["win_rate"] == 0.0
        assert stats["total_trades"] == 0

    def test_get_stats_after_trades(self, risk_manager):
        risk_manager.record_trade(size=100, price=0.5, pnl=20.0)
        risk_manager.record_trade(size=50, price=0.6, pnl=-10.0)
        risk_manager.record_trade(size=75, price=0.4, pnl=15.0)

        stats = risk_manager.get_stats()
        assert stats["total_trades"] == 3
        assert stats["total_pnl"] == 25.0
        assert stats["win_rate"] == pytest.approx(2 / 3, rel=0.01)

    def test_reset_daily_stats(self, risk_manager):
        risk_manager.daily_pnl = 100.0
        risk_manager.reset_daily_stats()
        assert risk_manager.daily_pnl == 0.0


class TestDynamicSizing:
    """Tests for dynamic position sizing with multiple factors."""

    def test_dynamic_reduces_on_losing_streak(self, risk_manager):
        size_normal = risk_manager._dynamic_size(price=0.5, confidence=0.7, lose_streak=0)
        size_losing = risk_manager._dynamic_size(price=0.5, confidence=0.7, lose_streak=3)
        assert size_losing < size_normal

    def test_dynamic_increases_on_winning_streak(self, risk_manager):
        size_normal = risk_manager._dynamic_size(price=0.5, confidence=0.7, win_streak=0)
        size_winning = risk_manager._dynamic_size(price=0.5, confidence=0.7, win_streak=5)
        assert size_winning > size_normal

    def test_dynamic_reduces_in_high_volatility(self, risk_manager):
        size_low_vol = risk_manager._dynamic_size(price=0.5, confidence=0.7, volatility=0.2)
        size_high_vol = risk_manager._dynamic_size(price=0.5, confidence=0.7, volatility=0.8)
        assert size_high_vol < size_low_vol

    def test_dynamic_reduces_after_losses(self, risk_manager):
        risk_manager.daily_pnl = -100.0  # Lost 50% of daily limit
        size = risk_manager._dynamic_size(price=0.5, confidence=0.7)

        risk_manager.daily_pnl = 0.0
        size_no_loss = risk_manager._dynamic_size(price=0.5, confidence=0.7)

        assert size < size_no_loss

    def test_dynamic_reduces_with_capital_drawdown(self, risk_manager):
        # Simulate 30% capital loss
        risk_manager.current_capital = 700.0
        size = risk_manager._dynamic_size(price=0.5, confidence=0.7)

        risk_manager.current_capital = 1000.0
        size_full_capital = risk_manager._dynamic_size(price=0.5, confidence=0.7)

        assert size < size_full_capital
