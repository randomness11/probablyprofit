import pytest
from probablyprofit.risk.manager import RiskManager, RiskLimits

@pytest.fixture
def risk_manager():
    return RiskManager(initial_capital=1000.0)

def test_initialization(risk_manager):
    assert risk_manager.current_capital == 1000.0
    assert risk_manager.current_exposure == 0.0

def test_can_open_position_valid(risk_manager):
    # Valid trade: $50 size, well within limits
    assert risk_manager.can_open_position(size=100, price=0.5) is True

def test_can_open_position_size_limit(risk_manager):
    # Default max position size is 100.0
    # Try to open $200 position
    assert risk_manager.can_open_position(size=400, price=0.5) is False

def test_can_open_position_daily_loss(risk_manager):
    risk_manager.daily_pnl = -300.0 # Exceeds default max daily loss of 200
    assert risk_manager.can_open_position(size=10, price=0.5) is False

def test_position_sizing_kelly(risk_manager):
    # Price 0.5 (odds = 1.0), Confidence 0.6 (60%)
    # Kelly = (0.6 * 1.0 - 0.4) / 1.0 = 0.2 (20%)
    # Max cap at 25%, so should return 20% of capital ($200) / price (0.5) = 400 shares
    
    # However, code also caps at max_position_size (default 100)
    # So expected is 100 / 0.5 = 200 shares
    
    risk_manager.limits.max_position_size = 1000.0  # Increase limit to test Kelly
    
    # 1. Full Kelly (0.25 default fraction? No, verify_kelly will check default)
    # With default fraction=0.25, it returns 0.2 * 0.25 = 0.05 (5%)
    # 5% of 1000 = 50. 50 / 0.5 = 100 shares.
    
    size = risk_manager.calculate_position_size(price=0.5, confidence=0.6, method="kelly")
    # Expected: Kelly=0.2, Fraction=0.25 -> 0.05. Capital=1000 -> 50. Price=0.5 -> 100 shares.
    assert size == 100.0

    # 2. Custom Fraction (e.g. 0.5)
    # returns 0.2 * 0.5 = 0.1 (10%)
    # 10% of 1000 = 100. 100 / 0.5 = 200 shares.
    size_half = risk_manager.calculate_position_size(
        price=0.5, confidence=0.6, method="kelly", kelly_fraction=0.5
    )
    assert size_half == 200.0

def test_stop_loss(risk_manager):
    # Entry 0.5, Current 0.3. Loss = 0.2. % Loss = 0.2/0.5 = 40%
    # Default stop loss is 20%
    assert risk_manager.should_stop_loss(entry_price=0.5, current_price=0.3, size=10) is True
    
    # Entry 0.5, Current 0.45. Loss = 0.05. % Loss = 10%
    assert risk_manager.should_stop_loss(entry_price=0.5, current_price=0.45, size=10) is False

def test_take_profit(risk_manager):
    # Entry 0.5, Current 0.8. Profit = 0.3. % Profit = 60%
    # Default take profit is 50%
    assert risk_manager.should_take_profit(entry_price=0.5, current_price=0.8, size=10) is True
