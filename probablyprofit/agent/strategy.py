"""
Trading Strategies

Defines modular strategies that determine:
1. Which markets to focus on (Market Filtering)
2. What instructions to give the AI (Prompt Generation)
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from probablyprofit.api.client import Market

class BaseStrategy(ABC):
    """Base class for trading strategies."""
    
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def filter_markets(self, markets: List[Market]) -> List[Market]:
        """
        Select relevant markets from the available list.
        """
        pass

    @abstractmethod
    def get_prompt(self) -> str:
        """
        Get the strategy instruction prompt for the AI.
        """
        pass


class MeanReversionStrategy(BaseStrategy):
    """
    Strategy that looks for price anomalies in binary markets.
    Focuses on tight spreads and potential overreactions.
    """
    
    def __init__(self, timeframe: str = "daily"):
        super().__init__(name="MeanReversion")
        self.timeframe = timeframe

    def filter_markets(self, markets: List[Market]) -> List[Market]:
        # Filter for active markets with decent liquidity/volume
        filtered = [
            m for m in markets 
            if m.active 
            and m.volume > 1000  # Min volume filter
            and len(m.outcomes) == 2 # Binary markets only for simplicity
        ]
        return filtered[:20] # Limit to top 20

    def get_prompt(self) -> str:
        return """
You are a Mean Reversion Trader.
Analyze the market prices. If a price is extremely high (>0.90) or low (<0.10) without definitive news confirmation, it might arguably be overbought/oversold.
However, be careful of "resolved" markets.
Look for discrepancies where the price doesn't match the fundamental probability.
Strategy:
- Buy 'No' if price > 0.85 and you believe the event is not certain.
- Buy 'Yes' if price < 0.15 and you believe the event is possible.
- Otherwise HOLD.
"""


class NewsTradingStrategy(BaseStrategy):
    """
    Strategy that trades based on specific keywords and news events.
    """
    
    def __init__(self, keywords: List[str]):
        super().__init__(name="NewsTrader")
        self.keywords = [k.lower() for k in keywords]

    def filter_markets(self, markets: List[Market]) -> List[Market]:
        filtered = []
        for m in markets:
            if not m.active:
                continue
            
            # Check if keywords match question or description
            text = (m.question + " " + (m.description or "")).lower()
            if any(k in text for k in self.keywords):
                filtered.append(m)
                
        return filtered

    def get_prompt(self) -> str:
        keywords_str = ", ".join(self.keywords)
        return f"""
You are a News-Based Event Trader.
You are extremely interested in markets containing these topics: {keywords_str}.
Analyze the market question carefully.
Strategy:
- If the news cycle strongly favors one outcome, bet on it.
- If the market is unrelated to the keywords despite the filter, IGNORE it (HOLD).
- Be aggressive if you have high confidence (>0.8).
"""


class CustomStrategy(BaseStrategy):
    """
    Strategy defined by the user via a text file or string.
    """
    
    def __init__(self, prompt_text: str, keywords: List[str] = None):
        super().__init__(name="CustomUserStrategy")
        self.prompt_text = prompt_text
        self.keywords = [k.lower() for k in keywords] if keywords else []

    def filter_markets(self, markets: List[Market]) -> List[Market]:
        # unique filtering logic: if keywords provided, filter by them.
        # otherwise return top active markets by volume.
        active_markets = [m for m in markets if m.active and m.volume > 0]
        
        if not self.keywords:
            # Sort by volume descending and take top 20
            active_markets.sort(key=lambda x: x.volume, reverse=True)
            return active_markets[:20]
            
        filtered = []
        for m in active_markets:
            text = (m.question + " " + (m.description or "")).lower()
            if any(k in text for k in self.keywords):
                filtered.append(m)
        return filtered

    def get_prompt(self) -> str:
        return self.prompt_text

