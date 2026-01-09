import pytest
from datetime import datetime
from probablyprofit.backtesting.engine import BacktestEngine
from probablyprofit.api.client import Market

def test_backtest_stats():
    engine = BacktestEngine(initial_capital=1000.0)
    
    # Simulate some equity history
    engine.equity_history = [
        {"equity": 1000.0},
        {"equity": 1100.0}, # +10%
        {"equity": 1210.0}, # +10%
    ]
    
    sharpe = engine._calculate_sharpe_ratio()
    # approx: mean(0.1, 0.1) / std(0.1, 0.1) -> tiny std -> huge sharpe
    assert sharpe > 0
    
    metrics = engine._calculate_results(datetime.now(), datetime.now())
    assert metrics.final_capital == 1210.0
    assert metrics.total_return_pct == 0.21

def test_max_drawdown():
    engine = BacktestEngine()
    engine.equity_history = [
        {"equity": 100},
        {"equity": 120}, # Peak
        {"equity": 90},  # Drop from 120 -> 90 is 30/120 = 25% DD
        {"equity": 110},
    ]
    
    dd = engine._calculate_max_drawdown()
    assert dd == 0.25
