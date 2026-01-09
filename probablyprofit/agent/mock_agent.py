"""
Mock Agent for Backtesting

A deterministic agent that doesn't require API calls, useful for:
- Fast backtesting
- Parameter optimization  
- CI/CD testing
"""

from typing import Optional
from datetime import datetime
from loguru import logger

from probablyprofit.agent.base import BaseAgent, Decision, Observation
from probablyprofit.api.client import PolymarketClient, Market
from probablyprofit.risk.manager import RiskManager


class MockAgent(BaseAgent):
    """
    Deterministic agent for testing.
    
    Uses simple rules instead of AI:
    - Buy when price < threshold
    - Sell when price > threshold
    - Configurable parameters for optimization
    """
    
    def __init__(
        self,
        client: PolymarketClient,
        risk_manager: RiskManager,
        buy_threshold: float = 0.4,
        sell_threshold: float = 0.6,
        confidence: float = 0.7,
        **kwargs
    ):
        super().__init__(
            client=client,
            risk_manager=risk_manager,
            **kwargs
        )
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold
        self.base_confidence = confidence
        
        logger.debug(f"MockAgent initialized: buy<{buy_threshold}, sell>{sell_threshold}")
    
    async def decide(self, observation: Observation) -> Decision:
        """Make decision based on simple rules."""
        
        if not observation.markets:
            return Decision(
                action="hold",
                market_id="",
                reasoning="No markets available"
            )
        
        # Find best opportunity
        best_buy: Optional[Market] = None
        best_sell: Optional[Market] = None
        
        for market in observation.markets:
            if not market.outcome_prices:
                continue
                
            price = market.outcome_prices[0]
            
            # Check for buy opportunity
            if price < self.buy_threshold:
                if not best_buy or price < best_buy.outcome_prices[0]:
                    best_buy = market
            
            # Check for sell in positions
            if market.condition_id in [p.market_id for p in observation.positions]:
                if price > self.sell_threshold:
                    if not best_sell or price > best_sell.outcome_prices[0]:
                        best_sell = market
        
        # Prioritize sells (realize profits)
        if best_sell:
            return Decision(
                action="sell",
                market_id=best_sell.condition_id,
                outcome=best_sell.outcomes[0] if best_sell.outcomes else "YES",
                size=10.0,  # Will be overridden by risk manager
                price=best_sell.outcome_prices[0],
                confidence=self.base_confidence,
                reasoning=f"Price {best_sell.outcome_prices[0]:.2f} > sell threshold {self.sell_threshold}"
            )
        
        # Then buys
        if best_buy:
            return Decision(
                action="buy",
                market_id=best_buy.condition_id,
                outcome=best_buy.outcomes[0] if best_buy.outcomes else "YES",
                size=10.0,
                price=best_buy.outcome_prices[0],
                confidence=self.base_confidence,
                reasoning=f"Price {best_buy.outcome_prices[0]:.2f} < buy threshold {self.buy_threshold}"
            )
        
        return Decision(
            action="hold",
            market_id="",
            reasoning="No opportunities found"
        )


def create_mock_agent_factory(client: PolymarketClient, risk: RiskManager):
    """
    Factory function for optimizer.
    
    Usage:
        factory = create_mock_agent_factory(client, risk)
        optimizer = StrategyOptimizer(agent_factory=factory)
    """
    def factory(params: dict) -> MockAgent:
        return MockAgent(
            client=client,
            risk_manager=risk,
            buy_threshold=params.get("buy_threshold", 0.4),
            sell_threshold=params.get("sell_threshold", 0.6),
            confidence=params.get("confidence", 0.7),
        )
    return factory
