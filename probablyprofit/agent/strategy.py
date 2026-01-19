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
            m
            for m in markets
            if m.active
            and m.volume > 1000  # Min volume filter
            and len(m.outcomes) == 2  # Binary markets only for simplicity
        ]
        return filtered[:20]  # Limit to top 20

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


class MomentumStrategy(BaseStrategy):
    """
    Strategy that follows price momentum.
    Buy when prices are moving in a clear direction.
    """

    def __init__(self, min_volume: float = 5000, lookback_hours: int = 24):
        super().__init__(name="Momentum")
        self.min_volume = min_volume
        self.lookback_hours = lookback_hours

    def filter_markets(self, markets: List[Market]) -> List[Market]:
        filtered = [
            m for m in markets if m.active and m.volume >= self.min_volume and len(m.outcomes) == 2
        ]
        # Sort by volume to get most active markets
        filtered.sort(key=lambda x: x.volume, reverse=True)
        return filtered[:15]

    def get_prompt(self) -> str:
        return f"""
You are a Momentum Trader analyzing prediction markets.
Your strategy is to follow price trends and ride momentum.

Analysis Framework:
1. Look at the current price relative to where it "should" be fundamentally
2. If price has been rising steadily, momentum is bullish - consider buying YES
3. If price has been falling steadily, momentum is bearish - consider buying NO
4. Avoid markets with choppy, sideways price action

Entry Criteria:
- Strong momentum: Price moved >10% in one direction recently
- Volume confirmation: Higher volume during price moves = stronger signal
- Don't fight the trend - go with momentum

Exit/Hold Criteria:
- If momentum is unclear or mixed, HOLD
- If price is at extreme levels (>95% or <5%), momentum may be exhausted
- Don't chase moves that are already extended

Risk Management:
- Position size based on momentum strength
- Higher confidence (0.7-0.9) for strong momentum
- Lower confidence (0.5-0.6) for weaker signals
"""


class ValueStrategy(BaseStrategy):
    """
    Strategy that looks for mispriced markets.
    Find markets where price doesn't reflect true probability.
    """

    def __init__(self, min_liquidity: float = 1000):
        super().__init__(name="Value")
        self.min_liquidity = min_liquidity

    def filter_markets(self, markets: List[Market]) -> List[Market]:
        filtered = [
            m
            for m in markets
            if m.active and m.liquidity >= self.min_liquidity and len(m.outcomes) == 2
        ]
        return filtered[:25]

    def get_prompt(self) -> str:
        return """
You are a Value Investor in prediction markets.
Your goal is to find markets where the price is WRONG relative to the true probability.

Value Identification:
1. Analyze the fundamental probability of each outcome
2. Compare your estimated probability to the current market price
3. If market price < your estimate by >15%, it's potentially undervalued (BUY YES)
4. If market price > your estimate by >15%, it's potentially overvalued (BUY NO)

What Creates Value Opportunities:
- Markets that aren't getting attention (low volume relative to importance)
- Recent news that hasn't been priced in yet
- Complex conditional outcomes that are hard to analyze
- Markets near resolution where outcome is clearer than price suggests

Decision Framework:
- Expected Value = (Your Probability * Payout) - (Price Paid)
- Only trade when Expected Value is significantly positive
- Confidence should reflect how certain you are about the mispricing

Avoid:
- Markets where you have no edge (you don't understand the topic better than others)
- Highly efficient markets with lots of volume
- Markets that are fairly priced
"""


class ContrarianStrategy(BaseStrategy):
    """
    Strategy that bets against the crowd.
    Look for overreactions and crowd psychology errors.
    """

    def __init__(self, extreme_threshold: float = 0.85):
        super().__init__(name="Contrarian")
        self.extreme_threshold = extreme_threshold

    def filter_markets(self, markets: List[Market]) -> List[Market]:
        # Look for markets at extreme prices
        filtered = []
        for m in markets:
            if not m.active or len(m.outcomes) != 2:
                continue
            yes_price = m.outcome_prices[0] if m.outcome_prices else 0.5
            # Filter for extreme prices
            if yes_price >= self.extreme_threshold or yes_price <= (1 - self.extreme_threshold):
                filtered.append(m)
        return filtered[:20]

    def get_prompt(self) -> str:
        return f"""
You are a Contrarian Trader.
You profit from crowd psychology errors and market overreactions.

Core Philosophy:
"Be fearful when others are greedy, and greedy when others are fearful."

What to Look For:
1. Markets at extreme prices (>{self.extreme_threshold:.0%} or <{1-self.extreme_threshold:.0%})
2. Prices driven by emotion rather than fundamentals
3. Situations where the crowd is likely wrong

Contrarian Signals:
- Price spike on news that doesn't fundamentally change probability
- Panic selling creating prices that seem "too low"
- Euphoria pushing prices that seem "too high"
- Markets where everyone agrees (consensus = opportunity)

Trading Rules:
- BUY NO when price >90% but outcome is not certain
- BUY YES when price <10% but outcome is still possible
- The greater the crowd certainty, the bigger the opportunity IF they're wrong
- Confidence = how confident you are the crowd is overreacting

Caution:
- Sometimes the crowd IS right - don't fight obvious outcomes
- Verify there's actual uncertainty before betting against the crowd
- Markets near resolution with clear outcomes should be avoided
"""


class VolatilityStrategy(BaseStrategy):
    """
    Strategy that trades during high volatility periods.
    Profits from price swings and uncertainty.
    """

    def __init__(self, min_volume: float = 2000):
        super().__init__(name="Volatility")
        self.min_volume = min_volume

    def filter_markets(self, markets: List[Market]) -> List[Market]:
        # Look for markets with prices in the "volatile" middle range
        filtered = []
        for m in markets:
            if not m.active or m.volume < self.min_volume:
                continue
            if len(m.outcomes) != 2:
                continue
            yes_price = m.outcome_prices[0] if m.outcome_prices else 0.5
            # Middle prices (30-70%) tend to be more volatile
            if 0.30 <= yes_price <= 0.70:
                filtered.append(m)
        # Sort by volume
        filtered.sort(key=lambda x: x.volume, reverse=True)
        return filtered[:20]

    def get_prompt(self) -> str:
        return """
You are a Volatility Trader specializing in prediction markets.
You profit from price swings and market uncertainty.

Strategy Overview:
Markets with prices between 30-70% are inherently uncertain and volatile.
Your edge comes from anticipating which way volatility will resolve.

What Creates Volatility:
- Upcoming events (debates, announcements, data releases)
- Breaking news that shifts probability
- Market disagreement about outcomes
- Time decay as expiration approaches

Trading Approach:
1. Identify markets with upcoming catalysts
2. Estimate which direction the catalyst will push prices
3. Position BEFORE the volatility event
4. Higher conviction = larger position

Entry Signals:
- Catalyst in next 24-72 hours
- Price in the 40-60% "maximum uncertainty" zone
- High volume indicating active interest
- Clear thesis on catalyst outcome

Confidence Levels:
- High (0.8+): Strong directional view on catalyst outcome
- Medium (0.6-0.8): Thesis but some uncertainty
- Low (0.5-0.6): Slight lean, smaller position

Risk: Volatility can go either way - only trade with clear conviction
"""


class CalendarStrategy(BaseStrategy):
    """
    Strategy based on upcoming events and deadlines.
    Trades markets approaching resolution or catalysts.
    """

    def __init__(self, days_until_expiry: int = 7):
        super().__init__(name="Calendar")
        self.days_until_expiry = days_until_expiry

    def filter_markets(self, markets: List[Market]) -> List[Market]:
        from datetime import datetime, timedelta

        cutoff = datetime.now() + timedelta(days=self.days_until_expiry)
        filtered = []
        for m in markets:
            if not m.active:
                continue
            # Filter for markets expiring soon
            if m.end_date and m.end_date <= cutoff:
                filtered.append(m)

        # Sort by end date (soonest first)
        filtered.sort(key=lambda x: x.end_date or datetime.max)
        return filtered[:20]

    def get_prompt(self) -> str:
        return f"""
You are a Calendar-Based Trader.
You specialize in markets approaching their resolution date.

Core Insight:
Markets expiring in the next {self.days_until_expiry} days offer unique opportunities because:
1. Uncertainty decreases as resolution approaches
2. Price should converge to true probability
3. Mispriced markets get corrected quickly

Strategy:
1. Focus on markets expiring within {self.days_until_expiry} days
2. Estimate the TRUE probability of each outcome
3. If market price ≠ your estimate, there's an opportunity
4. Near-expiry = higher confidence trades (less time for things to change)

Trade Types:
- Convergence Trade: Price is wrong and will correct before expiry
- Resolution Trade: You know outcome will be X, price doesn't fully reflect it
- Time Decay: Price should naturally move toward 0 or 100 as expiry nears

Entry Rules:
- Only trade markets you understand well
- Higher confidence for markets where outcome is becoming clear
- Consider time remaining - more time = more uncertainty

Exit:
- Hold until resolution OR
- Exit if your thesis changes

Risk Management:
- Near-expiry mistakes are costly - high conviction required
- Size positions based on time remaining and conviction
"""


class ArbitrageStrategy(BaseStrategy):
    """
    Strategy that looks for price discrepancies.
    Can be used for same-market arbitrage or cross-platform opportunities.
    """

    def __init__(self):
        super().__init__(name="Arbitrage")

    def filter_markets(self, markets: List[Market]) -> List[Market]:
        # Look for markets where YES + NO prices don't sum to ~1.0
        # or markets with unusual spreads
        filtered = []
        for m in markets:
            if not m.active or len(m.outcomes) != 2:
                continue
            yes_price = m.outcome_prices[0] if m.outcome_prices else 0.5
            no_price = m.outcome_prices[1] if len(m.outcome_prices) > 1 else 1 - yes_price

            # Check for mispricing (prices should sum to ~1.0)
            price_sum = yes_price + no_price
            if price_sum < 0.98 or price_sum > 1.02:
                filtered.append(m)
            # Also include liquid markets for cross-platform arb
            elif m.volume > 10000:
                filtered.append(m)

        return filtered[:20]

    def get_prompt(self) -> str:
        return """
You are an Arbitrage Trader in prediction markets.
You look for risk-free or low-risk profit opportunities from price discrepancies.

Types of Arbitrage:

1. Same-Market Arbitrage:
   - If YES + NO prices < 1.0, buy both for guaranteed profit
   - If YES + NO prices > 1.0, there's a spread to exploit
   - Example: YES @ 0.45 + NO @ 0.50 = 0.95 → Buy both, profit $0.05

2. Related Market Arbitrage:
   - Markets that should have related prices but don't
   - Example: "Trump wins" on two different market questions

Analysis Framework:
1. Calculate fair value for each side
2. Compare to actual market prices
3. Account for fees (typically 2% on Polymarket)
4. Only trade if profit > fees

Decision Output:
- If arbitrage exists: HIGH confidence BUY on underpriced side
- If no arbitrage: HOLD
- Never take large directional bets - arbitrage should be risk-free

Note: True arbitrage is rare. Most "arbitrage" opportunities disappear quickly.
"""
