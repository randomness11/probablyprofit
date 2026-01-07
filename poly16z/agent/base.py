"""
Base Agent

Core agent framework implementing the observe-decide-act loop.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from datetime import datetime
from loguru import logger
from pydantic import BaseModel

from poly16z.api.client import PolymarketClient, Market, Position, Order
from poly16z.risk.manager import RiskManager


class Observation(BaseModel):
    """Represents an observation of the market state."""

    timestamp: datetime
    markets: List[Market]
    positions: List[Position]
    balance: float
    signals: Dict[str, Any] = {}
    metadata: Dict[str, Any] = {}


class Decision(BaseModel):
    """Represents a trading decision."""

    action: str  # "buy", "sell", "hold", "close"
    market_id: Optional[str] = None
    outcome: Optional[str] = None
    size: float = 0.0
    price: Optional[float] = None
    reasoning: str = ""
    confidence: float = 0.5
    metadata: Dict[str, Any] = {}


class AgentMemory(BaseModel):
    """Agent memory for context persistence."""

    observations: List[Observation] = []
    decisions: List[Decision] = []
    trades: List[Order] = []
    metadata: Dict[str, Any] = {}

    def add_observation(self, observation: Observation) -> None:
        """Add observation to memory."""
        self.observations.append(observation)
        # Keep only last 100 observations
        if len(self.observations) > 100:
            self.observations = self.observations[-100:]

    def add_decision(self, decision: Decision) -> None:
        """Add decision to memory."""
        self.decisions.append(decision)
        if len(self.decisions) > 100:
            self.decisions = self.decisions[-100:]

    def add_trade(self, trade: Order) -> None:
        """Add trade to memory."""
        self.trades.append(trade)
        if len(self.trades) > 100:
            self.trades = self.trades[-100:]

    def get_recent_history(self, n: int = 10) -> str:
        """Get formatted recent history."""
        history = []
        for obs, dec in zip(self.observations[-n:], self.decisions[-n:]):
            history.append(
                f"Time: {obs.timestamp}\n"
                f"Markets observed: {len(obs.markets)}\n"
                f"Decision: {dec.action} - {dec.reasoning}\n"
            )
        return "\n".join(history)


class BaseAgent(ABC):
    """
    Base agent implementing the observe-decide-act loop.

    This is the core framework that all trading agents inherit from.
    Subclasses must implement the decide() method with their trading logic.
    """

    def __init__(
        self,
        client: PolymarketClient,
        risk_manager: RiskManager,
        name: str = "BaseAgent",
        loop_interval: int = 60,
    ):
        """
        Initialize base agent.

        Args:
            client: Polymarket API client
            risk_manager: Risk management system
            name: Agent name
            loop_interval: Seconds between loop iterations
        """
        self.client = client
        self.risk_manager = risk_manager
        self.name = name
        self.loop_interval = loop_interval

        self.memory = AgentMemory()
        self.running = False

        logger.info(f"Agent '{name}' initialized")

    async def observe(self) -> Observation:
        """
        Observe the current market state.

        Returns:
            Observation object containing market data, positions, etc.
        """
        logger.debug(f"[{self.name}] Observing market state...")

        # Fetch current data
        markets = await self.client.get_markets(active=True, limit=50)
        positions = await self.client.get_positions()
        balance = await self.client.get_balance()

        observation = Observation(
            timestamp=datetime.now(),
            markets=markets,
            positions=positions,
            balance=balance,
        )

        self.memory.add_observation(observation)
        logger.debug(f"[{self.name}] Observed {len(markets)} markets, {len(positions)} positions")

        return observation

    @abstractmethod
    async def decide(self, observation: Observation) -> Decision:
        """
        Make a trading decision based on observation.

        This is the core method that subclasses must implement with their
        trading strategy logic.

        Args:
            observation: Current market observation

        Returns:
            Decision object with trading action
        """
        pass

    async def act(self, decision: Decision) -> bool:
        """
        Execute a trading decision.

        Args:
            decision: Decision to execute

        Returns:
            True if action was successful
        """
        logger.info(f"[{self.name}] Acting on decision: {decision.action}")

        # Record decision
        self.memory.add_decision(decision)

        # Handle different actions
        if decision.action == "hold":
            logger.info(f"[{self.name}] Holding - no action taken")
            return True

        elif decision.action == "buy":
            if not decision.market_id or not decision.outcome:
                logger.error("Buy decision missing market_id or outcome")
                return False

            # Check risk limits
            if not self.risk_manager.can_open_position(decision.size, decision.price or 0.5):
                logger.warning("Risk manager rejected buy decision")
                return False

            # Place order
            order = await self.client.place_order(
                market_id=decision.market_id,
                outcome=decision.outcome,
                side="BUY",
                size=decision.size,
                price=decision.price or 0.5,
            )

            if order:
                self.memory.add_trade(order)
                self.risk_manager.record_trade(order.size, order.price)
                logger.info(f"[{self.name}] Buy order placed successfully")
                return True

            return False

        elif decision.action == "sell":
            if not decision.market_id or not decision.outcome:
                logger.error("Sell decision missing market_id or outcome")
                return False

            # Place sell order
            order = await self.client.place_order(
                market_id=decision.market_id,
                outcome=decision.outcome,
                side="SELL",
                size=decision.size,
                price=decision.price or 0.5,
            )

            if order:
                self.memory.add_trade(order)
                self.risk_manager.record_trade(-order.size, order.price)
                logger.info(f"[{self.name}] Sell order placed successfully")
                return True

            return False

        else:
            logger.warning(f"Unknown action: {decision.action}")
            return False

    async def run_loop(self) -> None:
        """
        Main agent loop: observe → decide → act.

        Runs continuously until stopped.
        """
        logger.info(f"[{self.name}] Starting agent loop (interval: {self.loop_interval}s)")
        self.running = True

        try:
            while self.running:
                try:
                    # Observe
                    observation = await self.observe()

                    # Decide
                    decision = await self.decide(observation)

                    # Act
                    success = await self.act(decision)

                    if success:
                        logger.info(f"[{self.name}] Loop iteration completed successfully")
                    else:
                        logger.warning(f"[{self.name}] Loop iteration failed")

                except Exception as e:
                    logger.error(f"[{self.name}] Error in agent loop: {e}")

                # Wait before next iteration
                await asyncio.sleep(self.loop_interval)

        except asyncio.CancelledError:
            logger.info(f"[{self.name}] Agent loop cancelled")
            self.running = False

    def stop(self) -> None:
        """Stop the agent loop."""
        logger.info(f"[{self.name}] Stopping agent...")
        self.running = False

    async def run(self) -> None:
        """
        Convenience method to run the agent.

        Usage:
            agent = MyAgent(client, risk_manager)
            await agent.run()
        """
        await self.run_loop()
