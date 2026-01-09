
import sys
import os

# Add parent directory to path to allow importing probablyprofit as a module
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from probablyprofit.agent.strategy import MeanReversionStrategy, NewsTradingStrategy
from probablyprofit.api.client import Market
from datetime import datetime

def test_strategy_filtering():
    print("Testing Strategy Filtering...")
    
    # Mock Markets
    m1 = Market(
        condition_id="1", question="Will Bitcoin hit 100k?", 
        outcome_prices=[0.6, 0.4], outcomes=["Yes", "No"], 
        volume=5000, liquidity=1000, end_date=datetime.now()
    )
    m2 = Market(
        condition_id="2", question="Will it rain in London?", 
        outcome_prices=[0.5, 0.5], outcomes=["Yes", "No"], 
        volume=50, liquidity=10, end_date=datetime.now()
    )
    m3 = Market(
        condition_id="3", question="Fed Interest Rate Decision", 
        outcome_prices=[0.9, 0.1], outcomes=["High", "Low"], 
        volume=10000, liquidity=5000, end_date=datetime.now()
    )
    
    markets = [m1, m2, m3]
    
    # Test Mean Reversion (should filter low volume m2)
    mr = MeanReversionStrategy()
    filtered_mr = mr.filter_markets(markets)
    print(f"Mean Reversion selected: {[m.question for m in filtered_mr]}")
    assert m2 not in filtered_mr
    assert m1 in filtered_mr
    
    # Test News Strategy (should filter for 'Bitcoin')
    news = NewsTradingStrategy(keywords=["Bitcoin"])
    filtered_news = news.filter_markets(markets)
    print(f"News Strategy selected: {[m.question for m in filtered_news]}")
    assert m1 in filtered_news
    assert m2 not in filtered_news
    assert m3 not in filtered_news

    print("Strategy tests passed!")

if __name__ == "__main__":
    test_strategy_filtering()
