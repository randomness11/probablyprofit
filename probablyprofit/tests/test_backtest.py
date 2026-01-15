from datetime import datetime

import pytest

from probablyprofit.api.client import Market
from probablyprofit.backtesting.engine import BacktestEngine


def test_backtest_stats():
    engine = BacktestEngine(initial_capital=1000.0)

    # Simulate some equity history with varying returns
    engine.equity_history = [
        {"equity": 1000.0},
        {"equity": 1100.0},  # +10%
        {"equity": 1155.0},  # +5%
        {"equity": 1213.0},  # +5%
    ]

    sharpe = engine._calculate_sharpe_ratio()
    # With varying returns, sharpe should be positive
    assert sharpe > 0

    metrics = engine._calculate_results(datetime.now(), datetime.now())
    assert metrics.final_capital == 1213.0
    assert metrics.total_return_pct == pytest.approx(0.213, rel=0.01)


def test_max_drawdown():
    engine = BacktestEngine()
    engine.equity_history = [
        {"equity": 100},
        {"equity": 120},  # Peak
        {"equity": 90},  # Drop from 120 -> 90 is 30/120 = 25% DD
        {"equity": 110},
    ]

    dd = engine._calculate_max_drawdown()
    assert dd == 0.25
