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

from probablyprofit.api.client import PolymarketClient, Market, Position, Order
from probablyprofit.risk.manager import RiskManager
# Note: Type checking import to avoid circular dependency if needed, but BaseStrategy doesn't import BaseAgent
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from probablyprofit.agent.strategy import BaseStrategy



class Observation(BaseModel):
    """Represents an observation of the market state."""

    timestamp: datetime
    markets: List[Market]
    positions: List[Position]
    balance: float
    signals: Dict[str, Any] = {}
    metadata: Dict[str, Any] = {}
    
    # Intelligence Layer (Phase 2)
    news_context: Optional[str] = None  # Formatted news summary
    sentiment_summary: Optional[str] = None  # Formatted sentiment analysis
    market_sentiments: Dict[str, Any] = {}  # market_id -> sentiment data



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
    """Agent memory for context persistence with optional database storage."""

    observations: List[Observation] = []
    decisions: List[Decision] = []
    trades: List[Order] = []
    metadata: Dict[str, Any] = {}

    # Database persistence
    enable_persistence: bool = False
    _db_manager: Any = None  # DatabaseManager instance
    _agent_name: str = "unknown"
    _agent_type: str = "unknown"

    def configure_persistence(self, db_manager: Any, agent_name: str = "unknown", agent_type: str = "unknown") -> None:
        """Enable database persistence."""
        self.enable_persistence = True
        self._db_manager = db_manager
        self._agent_name = agent_name
        self._agent_type = agent_type
        logger.info(f"AgentMemory: Database persistence enabled for {agent_name}")

    async def add_observation(self, observation: Observation) -> None:
        """Add observation to memory and optionally persist."""
        self.observations.append(observation)
        # Keep only last 100 observations
        if len(self.observations) > 100:
            self.observations = self.observations[-100:]

        # Persist to database
        if self.enable_persistence and self._db_manager:
            try:
                import json
                from probablyprofit.storage.repositories import ObservationRepository

                async with self._db_manager.get_session() as session:
                    await ObservationRepository.create(
                        session=session,
                        timestamp=observation.timestamp,
                        balance=observation.balance,
                        num_markets=len(observation.markets),
                        num_positions=len(observation.positions),
                        markets_json=json.dumps([m.model_dump(mode='json') for m in observation.markets]),
                        positions_json=json.dumps([p.model_dump(mode='json') for p in observation.positions]),
                        signals_json=json.dumps(observation.signals),
                        metadata_json=json.dumps(observation.metadata),
                        news_context=observation.news_context,
                        sentiment_summary=observation.sentiment_summary,
                    )
            except Exception as e:
                logger.warning(f"Failed to persist observation: {e}")

    async def add_decision(self, decision: Decision) -> None:
        """Add decision to memory and optionally persist."""
        self.decisions.append(decision)
        if len(self.decisions) > 100:
            self.decisions = self.decisions[-100:]

        # Persist to database
        if self.enable_persistence and self._db_manager:
            try:
                import json
                from probablyprofit.storage.repositories import DecisionRepository

                async with self._db_manager.get_session() as session:
                    await DecisionRepository.create(
                        session=session,
                        action=decision.action,
                        market_id=decision.market_id,
                        outcome=decision.outcome,
                        size=decision.size,
                        price=decision.price,
                        reasoning=decision.reasoning,
                        confidence=decision.confidence,
                        metadata_json=json.dumps(decision.metadata),
                        agent_name=self._agent_name,
                        agent_type=self._agent_type,
                    )
            except Exception as e:
                logger.warning(f"Failed to persist decision: {e}")

    async def add_trade(self, trade: Order) -> None:
        """Add trade to memory and optionally persist."""
        self.trades.append(trade)
        if len(self.trades) > 100:
            self.trades = self.trades[-100:]

        # Persist to database
        if self.enable_persistence and self._db_manager:
            try:
                from probablyprofit.storage.repositories import TradeRepository

                async with self._db_manager.get_session() as session:
                    await TradeRepository.create(
                        session=session,
                        order_id=trade.order_id,
                        market_id=trade.market_id,
                        outcome=trade.outcome,
                        side=trade.side,
                        size=trade.size,
                        price=trade.price,
                        status=trade.status,
                        filled_size=trade.filled_size,
                        timestamp=trade.timestamp,
                    )
            except Exception as e:
                logger.warning(f"Failed to persist trade: {e}")

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
        strategy: Optional['BaseStrategy'] = None,
        dry_run: bool = False,
        enable_persistence: bool = True,
    ):
        """
        Initialize base agent.

        Args:
            client: Polymarket API client
            risk_manager: Risk management system
            name: Agent name
            loop_interval: Seconds between loop intervals
            strategy: Optional strategy to filter markets
            dry_run: If True, log decisions but don't place real trades
            enable_persistence: If True, enable database persistence
        """
        self.client = client
        self.risk_manager = risk_manager
        self.name = name
        self.loop_interval = loop_interval
        self.strategy = strategy
        self.dry_run = dry_run

        # Sizing configuration
        self.sizing_method = "manual"  # manual, fixed_pct, kelly, confidence_based
        self.kelly_fraction = 0.25

        self.memory = AgentMemory()
        self.running = False

        # Setup database persistence if enabled
        if enable_persistence:
            try:
                from probablyprofit.storage.database import get_db_manager

                db_manager = get_db_manager()
                agent_type = self.__class__.__name__.replace("Agent", "").lower()
                self.memory.configure_persistence(db_manager, agent_name=name, agent_type=agent_type)
            except Exception as e:
                logger.warning(f"Could not enable database persistence: {e}")

        mode_str = " [DRY RUN MODE]" if dry_run else ""
        logger.info(f"Agent '{name}' initialized{mode_str}")

    async def observe(self) -> Observation:
        """
        Observe the current market state.

        Returns:
            Observation object containing market data, positions, etc.
        """
        logger.debug(f"[{self.name}] Observing market state...")

        # Fetch current data
        markets = await self.client.get_markets(active=True, limit=50)
        
        # Apply Strategy Filtering if present
        if self.strategy:
            original_count = len(markets)
            markets = self.strategy.filter_markets(markets)
            logger.debug(f"[{self.name}] Strategy '{self.strategy.name}' filtered markets: {original_count} -> {len(markets)}")

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
                
            # Apply Auto-Sizing if enabled
            if self.sizing_method != "manual" and decision.price:
                original_size = decision.size
                decision.size = self.risk_manager.calculate_position_size(
                    price=decision.price,
                    confidence=decision.confidence,
                    method=self.sizing_method,
                    kelly_fraction=self.kelly_fraction
                )
                if decision.size != original_size:
                    logger.info(
                        f"[{self.name}] 📏 Auto-sized trade: {original_size:.2f} -> {decision.size:.2f} "
                        f"({self.sizing_method})"
                    )

            # Check risk limits
            if not self.risk_manager.can_open_position(decision.size, decision.price or 0.5):
                logger.warning("Risk manager rejected buy decision")
                return False

            # Dry run check
            if self.dry_run:
                logger.info(f"[{self.name}] 🧪 DRY RUN: Would BUY {decision.size} of '{decision.outcome}' @ {decision.price:.2f} on {decision.market_id}")
                return True

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

            # Dry run check
            if self.dry_run:
                logger.info(f"[{self.name}] 🧪 DRY RUN: Would SELL {decision.size} of '{decision.outcome}' @ {decision.price:.2f} on {decision.market_id}")
                return True

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
