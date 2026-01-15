"""Cross-platform arbitrage detection."""

from probablyprofit.arbitrage.detector import ArbitrageDetector, ArbitrageOpportunity, MarketPair
from probablyprofit.arbitrage.matcher import MarketMatcher, MatchResult

__all__ = [
    "ArbitrageDetector",
    "ArbitrageOpportunity",
    "MarketPair",
    "MarketMatcher",
    "MatchResult",
]
