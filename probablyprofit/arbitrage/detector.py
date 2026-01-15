"""
Arbitrage Detector

Detects price discrepancies between Polymarket and Kalshi
for profitable arbitrage opportunities.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger
from pydantic import BaseModel

from probablyprofit.arbitrage.matcher import MarketMatcher, MatchResult
from probablyprofit.config import get_config


class MarketPair(BaseModel):
    """A matched pair of markets across platforms."""

    polymarket_id: str
    polymarket_question: str
    polymarket_yes_price: float
    polymarket_no_price: float

    kalshi_ticker: str
    kalshi_question: str
    kalshi_yes_price: float
    kalshi_no_price: float

    similarity_score: float
    matched_keywords: List[str] = []


class ArbitrageOpportunity(BaseModel):
    """
    Represents an arbitrage opportunity between two markets.

    An arbitrage exists when:
    - YES on Platform A + NO on Platform B < 1.0 (or vice versa)
    - After fees, there's still profit
    """

    pair: MarketPair
    opportunity_type: str  # "yes_poly_no_kalshi" or "no_poly_yes_kalshi"

    # Prices
    buy_platform: str  # "polymarket" or "kalshi"
    buy_side: str  # "yes" or "no"
    buy_price: float

    sell_platform: str
    sell_side: str
    sell_price: float

    # Profit calculation
    combined_cost: float  # Cost to buy both sides
    gross_profit: float  # Raw profit per $1 invested
    gross_profit_pct: float

    # After fees
    estimated_fees: float
    net_profit: float
    net_profit_pct: float

    # Risk metrics
    price_spread: float
    confidence: float  # Based on match quality and liquidity
    expires_at: Optional[datetime] = None

    # Metadata
    detected_at: datetime = field(default_factory=datetime.now)

    class Config:
        arbitrary_types_allowed = True

    def format_for_display(self) -> str:
        """Format opportunity for display."""
        return (
            f"🎯 ARBITRAGE: {self.net_profit_pct:+.1%} profit\n"
            f"   Buy {self.buy_side.upper()} on {self.buy_platform} @ {self.buy_price:.2%}\n"
            f"   Sell {self.sell_side.upper()} on {self.sell_platform} @ {self.sell_price:.2%}\n"
            f"   Market: {self.pair.polymarket_question[:50]}...\n"
            f"   Confidence: {self.confidence:.0%}"
        )


class ArbitrageDetector:
    """
    Detects cross-platform arbitrage opportunities.

    Monitors price differences between Polymarket and Kalshi
    and identifies profitable arbitrage when prices diverge.

    Example:
        detector = ArbitrageDetector(
            polymarket_client=poly_client,
            kalshi_client=kalshi_client,
        )
        opportunities = await detector.scan()
        for opp in opportunities:
            print(opp.format_for_display())
    """

    def __init__(
        self,
        polymarket_client: Any = None,
        kalshi_client: Any = None,
    ):
        """
        Initialize arbitrage detector.

        Args:
            polymarket_client: Polymarket API client
            kalshi_client: Kalshi API client
        """
        self.polymarket_client = polymarket_client
        self.kalshi_client = kalshi_client

        # Load config from global config
        cfg = get_config()
        self.min_profit_pct = cfg.arbitrage.min_profit_pct
        self.polymarket_fee = cfg.arbitrage.polymarket_fee
        self.kalshi_fee = cfg.arbitrage.kalshi_fee
        self.min_match_similarity = cfg.arbitrage.min_match_similarity

        self.matcher = MarketMatcher(min_similarity=self.min_match_similarity)

        # Cache for matched pairs
        self._matched_pairs: List[MarketPair] = []
        self._last_scan: Optional[datetime] = None
        self._opportunities: List[ArbitrageOpportunity] = []

    async def scan(
        self,
        force_refresh: bool = False,
    ) -> List[ArbitrageOpportunity]:
        """
        Scan for arbitrage opportunities.

        Args:
            force_refresh: Force re-fetch of market data

        Returns:
            List of arbitrage opportunities sorted by profit
        """
        logger.info("🔍 Scanning for arbitrage opportunities...")

        # Fetch markets from both platforms
        poly_markets = []
        kalshi_markets = []

        if self.polymarket_client:
            try:
                poly_markets = await self.polymarket_client.get_markets(active=True, limit=100)
                logger.info(f"Fetched {len(poly_markets)} Polymarket markets")
            except Exception as e:
                logger.error(f"Failed to fetch Polymarket markets: {e}")

        if self.kalshi_client:
            try:
                kalshi_markets = await self.kalshi_client.get_markets(status="open", limit=100)
                logger.info(f"Fetched {len(kalshi_markets)} Kalshi markets")
            except Exception as e:
                logger.error(f"Failed to fetch Kalshi markets: {e}")

        if not poly_markets or not kalshi_markets:
            logger.warning("Insufficient market data for arbitrage detection")
            return []

        # Match markets between platforms
        matches = self.matcher.match_markets(poly_markets, kalshi_markets)
        logger.info(f"Found {len(matches)} matched market pairs")

        # Build market pairs with prices
        self._matched_pairs = []
        for match in matches:
            if not match.is_strong_match:
                continue

            # Find the actual market objects
            poly_market = next(
                (m for m in poly_markets if m.condition_id == match.polymarket_id),
                None,
            )
            kalshi_market = next(
                (m for m in kalshi_markets if m.ticker == match.kalshi_ticker),
                None,
            )

            if poly_market and kalshi_market:
                pair = MarketPair(
                    polymarket_id=match.polymarket_id,
                    polymarket_question=match.polymarket_question,
                    polymarket_yes_price=poly_market.outcome_prices[0],
                    polymarket_no_price=(
                        poly_market.outcome_prices[1]
                        if len(poly_market.outcome_prices) > 1
                        else 1 - poly_market.outcome_prices[0]
                    ),
                    kalshi_ticker=match.kalshi_ticker,
                    kalshi_question=match.kalshi_question,
                    kalshi_yes_price=kalshi_market.outcome_prices[0],
                    kalshi_no_price=(
                        kalshi_market.outcome_prices[1]
                        if len(kalshi_market.outcome_prices) > 1
                        else 1 - kalshi_market.outcome_prices[0]
                    ),
                    similarity_score=match.similarity_score,
                    matched_keywords=match.matched_keywords,
                )
                self._matched_pairs.append(pair)

        # Detect arbitrage opportunities
        self._opportunities = []
        for pair in self._matched_pairs:
            opps = self._detect_opportunities(pair)
            self._opportunities.extend(opps)

        # Sort by profit and limit
        self._opportunities.sort(key=lambda o: o.net_profit_pct, reverse=True)
        self._opportunities = self._opportunities[: 10]

        self._last_scan = datetime.now()

        logger.info(f"🎯 Found {len(self._opportunities)} arbitrage opportunities")
        for opp in self._opportunities[:3]:  # Log top 3
            logger.info(opp.format_for_display())

        return self._opportunities

    def _detect_opportunities(
        self,
        pair: MarketPair,
    ) -> List[ArbitrageOpportunity]:
        """
        Detect arbitrage opportunities for a market pair.

        Arbitrage exists when:
        1. YES on Poly + NO on Kalshi < 1.0 (profit = 1.0 - combined)
        2. NO on Poly + YES on Kalshi < 1.0 (profit = 1.0 - combined)
        """
        opportunities = []

        # Strategy 1: Buy YES on Polymarket, Buy NO on Kalshi
        combined_1 = pair.polymarket_yes_price + pair.kalshi_no_price
        if combined_1 < 1.0:
            gross_profit = 1.0 - combined_1
            fees = self._calculate_fees(pair.polymarket_yes_price, pair.kalshi_no_price)
            net_profit = gross_profit - fees

            if net_profit / combined_1 >= self.min_profit_pct:
                opp = ArbitrageOpportunity(
                    pair=pair,
                    opportunity_type="yes_poly_no_kalshi",
                    buy_platform="polymarket",
                    buy_side="yes",
                    buy_price=pair.polymarket_yes_price,
                    sell_platform="kalshi",
                    sell_side="no",
                    sell_price=pair.kalshi_no_price,
                    combined_cost=combined_1,
                    gross_profit=gross_profit,
                    gross_profit_pct=gross_profit / combined_1,
                    estimated_fees=fees,
                    net_profit=net_profit,
                    net_profit_pct=net_profit / combined_1,
                    price_spread=abs(pair.polymarket_yes_price - (1 - pair.kalshi_no_price)),
                    confidence=self._calculate_confidence(pair),
                )
                opportunities.append(opp)

        # Strategy 2: Buy NO on Polymarket, Buy YES on Kalshi
        combined_2 = pair.polymarket_no_price + pair.kalshi_yes_price
        if combined_2 < 1.0:
            gross_profit = 1.0 - combined_2
            fees = self._calculate_fees(pair.polymarket_no_price, pair.kalshi_yes_price)
            net_profit = gross_profit - fees

            if net_profit / combined_2 >= self.min_profit_pct:
                opp = ArbitrageOpportunity(
                    pair=pair,
                    opportunity_type="no_poly_yes_kalshi",
                    buy_platform="polymarket",
                    buy_side="no",
                    buy_price=pair.polymarket_no_price,
                    sell_platform="kalshi",
                    sell_side="yes",
                    sell_price=pair.kalshi_yes_price,
                    combined_cost=combined_2,
                    gross_profit=gross_profit,
                    gross_profit_pct=gross_profit / combined_2,
                    estimated_fees=fees,
                    net_profit=net_profit,
                    net_profit_pct=net_profit / combined_2,
                    price_spread=abs(pair.polymarket_no_price - (1 - pair.kalshi_yes_price)),
                    confidence=self._calculate_confidence(pair),
                )
                opportunities.append(opp)

        return opportunities

    def _calculate_fees(
        self,
        poly_price: float,
        kalshi_price: float,
    ) -> float:
        """Calculate estimated trading fees."""
        poly_fee = poly_price * self.polymarket_fee
        kalshi_fee = kalshi_price * self.kalshi_fee
        return poly_fee + kalshi_fee

    def _calculate_confidence(self, pair: MarketPair) -> float:
        """
        Calculate confidence score for an arbitrage opportunity.

        Based on:
        - Market match quality
        - Price stability (spread)
        - Market liquidity
        """
        # Base confidence from match similarity
        confidence = pair.similarity_score

        # Reduce confidence for large price spreads (might be stale)
        price_diff = abs(pair.polymarket_yes_price - pair.kalshi_yes_price)
        if price_diff > 0.20:
            confidence *= 0.7
        elif price_diff > 0.10:
            confidence *= 0.85

        return min(1.0, confidence)

    def get_opportunities(self) -> List[ArbitrageOpportunity]:
        """Get cached opportunities from last scan."""
        return self._opportunities

    def get_matched_pairs(self) -> List[MarketPair]:
        """Get all matched market pairs."""
        return self._matched_pairs

    async def monitor(
        self,
        interval_seconds: int = 60,
        callback: Optional[callable] = None,
    ):
        """
        Continuously monitor for arbitrage opportunities.

        Args:
            interval_seconds: Scan interval
            callback: Function to call when opportunities found
        """
        logger.info(f"Starting arbitrage monitor (interval: {interval_seconds}s)")

        while True:
            try:
                opportunities = await self.scan()

                if opportunities and callback:
                    await callback(opportunities)

            except Exception as e:
                logger.error(f"Error in arbitrage monitor: {e}")

            await asyncio.sleep(interval_seconds)

    def simulate_execution(
        self,
        opportunity: ArbitrageOpportunity,
        capital: float,
    ) -> Dict[str, Any]:
        """
        Simulate executing an arbitrage opportunity.

        Args:
            opportunity: The opportunity to simulate
            capital: Capital to deploy

        Returns:
            Simulation results
        """
        # Split capital between both sides
        half_capital = capital / 2

        # Calculate shares on each platform
        poly_shares = half_capital / opportunity.buy_price
        kalshi_shares = half_capital / opportunity.sell_price

        # Use minimum shares (can only profit on matched quantity)
        shares = min(poly_shares, kalshi_shares)

        # Calculate returns
        total_cost = shares * opportunity.combined_cost
        gross_return = shares * 1.0  # Win $1 per share guaranteed
        fees = shares * opportunity.estimated_fees
        net_return = gross_return - fees

        profit = net_return - total_cost

        return {
            "capital_deployed": total_cost,
            "shares": shares,
            "gross_return": gross_return,
            "fees": fees,
            "net_return": net_return,
            "profit": profit,
            "profit_pct": profit / total_cost if total_cost > 0 else 0,
            "roi": profit / capital if capital > 0 else 0,
        }
