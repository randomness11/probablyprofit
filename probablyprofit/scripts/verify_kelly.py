
import sys
import os
# Add project root to path
# scripts/ is at <root>/probablyprofit/scripts/
# We want to add <root> so we can import probablyprofit
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from probablyprofit.risk.manager import RiskManager

def test_kelly():
    print("🧪 Testing Kelly Criterion Logic...")
    
    risk = RiskManager(initial_capital=1000.0)
    # Increase max position size to not cap our tests
    risk.limits.max_position_size = 10000.0
    
    # Scenario:
    # Price = 0.5 (Implied odds = 1:1)
    # Win Prob = 0.6 (60%)
    # Kelly % = Win - Loss/Odds = 0.6 - 0.4/1 = 0.2 (20%)
    
    import math
    
    # 1. Default Quarter Kelly (fraction=0.25)
    # Allocation = 20% * 0.25 = 5%
    # Position Value = $1000 * 5% = $50
    # Size = $50 / 0.5 = 100 shares
    
    size_q = risk.calculate_position_size(0.5, 0.6, method="kelly")
    print(f"Quarter Kelly (default): {size_q} shares (Expected: 100.0)")
    assert math.isclose(size_q, 100.0, rel_tol=1e-9), f"Expected 100.0, got {size_q}"
    
    # 2. Half Kelly (fraction=0.5)
    # Allocation = 20% * 0.5 = 10%
    # Position Value = $1000 * 10% = $100
    # Size = $100 / 0.5 = 200 shares
    
    size_h = risk.calculate_position_size(0.5, 0.6, method="kelly", kelly_fraction=0.5)
    print(f"Half Kelly: {size_h} shares (Expected: 200.0)")
    assert math.isclose(size_h, 200.0, rel_tol=1e-9), f"Expected 200.0, got {size_h}"
    
    # 3. Negative Edge (Price 0.5, Win Prob 0.4)
    # Kelly = 0.4 - 0.6 = -0.2 (Should be 0)
    size_neg = risk.calculate_position_size(0.5, 0.4, method="kelly")
    print(f"Negative Edge: {size_neg} shares (Expected: 0.0)")
    assert size_neg == 0.0, f"Expected 0.0, got {size_neg}"

    print("✅ Kelly Logic Verified!")

if __name__ == "__main__":
    try:
        test_kelly()
    except AssertionError as e:
        print(f"❌ Test Failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"💥 Error: {e}")
        sys.exit(1)
