"""
Base Agent

Core agent framework implementing the observe-decide-act loop.
"""

import asyncio
from abc import ABC, abstractmethod
from collections import deque
from datetime import datetime

# Note: Type checking import to avoid circular dependency if needed, but BaseStrategy doesn't import BaseAgent
from typing import TYPE_CHECKING, Any, Deque, Dict, List, Optional

from loguru import logger
from pydantic import BaseModel, ConfigDict

from probablyprofit.alerts.telegram import get_alerter
from probablyprofit.api.client import Market, Order, PolymarketClient, Position
from probablyprofit.config import get_config
from probablyprofit.risk.manager import RiskManager
from probablyprofit.utils.killswitch import KillSwitchError, get_kill_switch, is_kill_switch_active

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
    """Agent memory for context persistence with optional database storage.

    Thread-safe for concurrent access using asyncio.Lock.
    """

    # Use deque with maxlen to prevent unbounded memory growth
    # Note: Pydantic v2 handles deque serialization automatically
    model_config = ConfigDict(arbitrary_types_allowed=True)

    observations: Deque[Observation] = deque(maxlen=100)
    decisions: Deque[Decision] = deque(maxlen=100)
    trades: Deque[Order] = deque(maxlen=100)
    metadata: Dict[str, Any] = {}

    # Database persistence
    enable_persistence: bool = False
    _db_manager: Any = None  # DatabaseManager instance
    _agent_name: str = "unknown"
    _agent_type: str = "unknown"

    # Thread safety lock (initialized in __init__)
    _lock: Any = None

    def __init__(self, **data):
        """Initialize with proper deque instances."""
        super().__init__(**data)

        # Initialize lock for thread safety
        self._lock = asyncio.Lock()

        # Get memory limits from config
        cfg = get_config()
        max_obs = cfg.agent.memory_max_observations
        max_dec = cfg.agent.memory_max_decisions
        max_trades = cfg.agent.memory_max_trades

        # Ensure deques are properly initialized with maxlen from config
        if not isinstance(self.observations, deque) or self.observations.maxlen != max_obs:
            self.observations = deque(self.observations, maxlen=max_obs)
        if not isinstance(self.decisions, deque) or self.decisions.maxlen != max_dec:
            self.decisions = deque(self.decisions, maxlen=max_dec)
        if not isinstance(self.trades, deque) or self.trades.maxlen != max_trades:
            self.trades = deque(self.trades, maxlen=max_trades)

    def configure_persistence(
        self, db_manager: Any, agent_name: str = "unknown", agent_type: str = "unknown"
    ) -> None:
        """Enable database persistence."""
        self.enable_persistence = True
        self._db_manager = db_manager
        self._agent_name = agent_name
        self._agent_type = agent_type
        logger.info(f"AgentMemory: Database persistence enabled for {agent_name}")

    async def add_observation(self, observation: Observation) -> None:
        """Add observation to memory and optionally persist (thread-safe)."""
        async with self._lock:
            # deque with maxlen automatically evicts oldest items
            self.observations.append(observation)

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
                        markets_json=json.dumps(
                            [m.model_dump(mode="json") for m in observation.markets]
                        ),
                        positions_json=json.dumps(
                            [p.model_dump(mode="json") for p in observation.positions]
                        ),
                        signals_json=json.dumps(observation.signals),
                        metadata_json=json.dumps(observation.metadata),
                        news_context=observation.news_context,
                        sentiment_summary=observation.sentiment_summary,
                    )
            except Exception as e:
                logger.warning(f"Failed to persist observation: {e}")

    async def add_decision(self, decision: Decision) -> None:
        """Add decision to memory and optionally persist (thread-safe)."""
        async with self._lock:
            # deque with maxlen automatically evicts oldest items
            self.decisions.append(decision)

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
        """Add trade to memory and optionally persist (thread-safe)."""
        async with self._lock:
            # deque with maxlen automatically evicts oldest items
            self.trades.append(trade)

        # Persist to database
        if self.enable_persistence and self._db_manager:
            try:
                from probablyprofit.storage.repositories import TradeRepository

                async with self._db_manager.get_session() as session:
                    await TradeRepository.create(
                        session=session,
                        order_id=trade.order_id,
                        market_id=trade.market_id,
                        market_question=trade.market_question,  # For searchable trade history
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
        """Get formatted recent history.

        Note: This creates atomic snapshots of the deques, which is thread-safe
        for reading even without locks in Python due to the GIL.
        """
        history = []
        # Create atomic snapshots by converting to lists (safe due to GIL)
        obs_list = list(self.observations)[-n:]
        dec_list = list(self.decisions)[-n:]
        for obs, dec in zip(obs_list, dec_list):
            history.append(
                f"Time: {obs.timestamp}\n"
                f"Markets observed: {len(obs.markets)}\n"
                f"Decision: {dec.action} - {dec.reasoning}\n"
            )
        return "\n".join(history)

    async def get_recent_history_async(self, n: int = 10) -> str:
        """Get formatted recent history (async thread-safe version)."""
        async with self._lock:
            return self.get_recent_history(n)


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
        strategy: Optional["BaseStrategy"] = None,
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

        # Thread-safe running state using asyncio.Event
        self._stop_event = asyncio.Event()
        self._running = False  # For synchronous checks only

        # Track open positions to avoid duplicates
        self._open_positions: set = set()  # Set of market_id:outcome

        # Cache market names for better logging
        self._market_names: dict = {}  # market_id -> question

        # Setup database persistence if enabled
        if enable_persistence:
            try:
                from probablyprofit.storage.database import get_db_manager

                db_manager = get_db_manager()
                agent_type = self.__class__.__name__.replace("Agent", "").lower()
                self.memory.configure_persistence(
                    db_manager, agent_name=name, agent_type=agent_type
                )
            except Exception as e:
                logger.warning(f"Could not enable database persistence: {e}")

        mode_str = " [DRY RUN MODE]" if dry_run else ""
        logger.info(f"Agent '{name}' initialized{mode_str}")

    @property
    def running(self) -> bool:
        """Check if agent is running (thread-safe)."""
        return self._running and not self._stop_event.is_set()

    @running.setter
    def running(self, value: bool) -> None:
        """Set running state (for backwards compatibility)."""
        self._running = value
        if not value:
            self._stop_event.set()
        else:
            self._stop_event.clear()

    def _get_market_name(self, market_id: str, max_len: int = 60) -> str:
        """Get human-readable market name from ID."""
        name = self._market_names.get(market_id, market_id[:20] + "...")
        if len(name) > max_len:
            name = name[: max_len - 3] + "..."
        return name

    def _has_position(self, market_id: str, outcome: str) -> bool:
        """Check if we already have a position in this market."""
        key = f"{market_id}:{outcome}"
        return key in self._open_positions

    def _record_position(self, market_id: str, outcome: str) -> None:
        """Record that we have a position in this market."""
        key = f"{market_id}:{outcome}"
        self._open_positions.add(key)

    async def observe(self) -> Observation:
        """
        Observe the current market state.

        Returns:
            Observation object containing market data, positions, etc.
        """
        logger.debug(f"[{self.name}] Observing market state...")

        # Fetch current data
        markets = await self.client.get_markets(active=True, limit=50)

        # Cache market names for better logging
        for market in markets:
            self._market_names[market.condition_id] = market.question

        # Apply Strategy Filtering if present
        if self.strategy:
            original_count = len(markets)
            markets = self.strategy.filter_markets(markets)
            logger.debug(
                f"[{self.name}] Strategy '{self.strategy.name}' filtered markets: {original_count} -> {len(markets)}"
            )

        positions = await self.client.get_positions()

        # Sync tracked positions with actual positions
        # In dry run mode, keep our local tracking (API returns nothing)
        # In live mode, sync with actual positions from API
        if not self.dry_run or not self._open_positions:
            # Only reset if we're live or have no local tracking
            api_positions = set()
            for pos in positions:
                if pos.size > 0:
                    key = f"{pos.market_id}:{pos.outcome}"
                    api_positions.add(key)
            # In live mode, use API positions; in dry run, merge with local
            if not self.dry_run:
                self._open_positions = api_positions
            else:
                # Dry run: add any API positions but keep our local ones too
                self._open_positions.update(api_positions)

        balance = await self.client.get_balance()

        observation = Observation(
            timestamp=datetime.now(),
            markets=markets,
            positions=positions,
            balance=balance,
        )

        await self.memory.add_observation(observation)
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
        await self.memory.add_decision(decision)

        # Handle different actions
        if decision.action == "hold":
            logger.info(f"[{self.name}] Holding - no action taken")
            return True

        elif decision.action == "buy":
            if not decision.market_id or not decision.outcome:
                logger.error("Buy decision missing market_id or outcome")
                return False

            # Get readable market name
            market_name = self._get_market_name(decision.market_id)

            # Check if we already have a position (avoid duplicate buys)
            if self._has_position(decision.market_id, decision.outcome):
                logger.info(
                    f"[{self.name}] ⏭️ Already have position in '{market_name}' ({decision.outcome}) - skipping"
                )
                return True  # Not an error, just skip

            # Apply Auto-Sizing if enabled
            if self.sizing_method != "manual" and decision.price:
                original_size = decision.size
                decision.size = self.risk_manager.calculate_position_size(
                    price=decision.price,
                    confidence=decision.confidence,
                    method=self.sizing_method,
                    kelly_fraction=self.kelly_fraction,
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
                logger.info(
                    f"[{self.name}] 🧪 DRY RUN: Would BUY ${decision.size:.2f} of '{decision.outcome}' @ {decision.price:.2f}"
                )
                logger.info(f"[{self.name}] 📊 Market: {market_name}")
                # Track position even in dry run
                self._record_position(decision.market_id, decision.outcome)
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
                await self.memory.add_trade(order)
                self.risk_manager.record_trade(order.size, order.price)
                self._record_position(decision.market_id, decision.outcome)
                logger.info(
                    f"[{self.name}] ✅ BUY order placed: ${decision.size:.2f} on '{market_name}'"
                )
                # Send trade alert
                try:
                    alerter = get_alerter()
                    await alerter.alert_trade_executed(
                        market=market_name,
                        side="BUY",
                        size=order.size,
                        price=order.price,
                    )
                except Exception:
                    pass
                return True

            return False

        elif decision.action == "sell":
            if not decision.market_id or not decision.outcome:
                logger.error("Sell decision missing market_id or outcome")
                return False

            # Get readable market name
            market_name = self._get_market_name(decision.market_id)

            # Dry run check
            if self.dry_run:
                logger.info(
                    f"[{self.name}] 🧪 DRY RUN: Would SELL ${decision.size:.2f} of '{decision.outcome}' @ {decision.price:.2f}"
                )
                logger.info(f"[{self.name}] 📊 Market: {market_name}")
                # Remove from tracked positions
                key = f"{decision.market_id}:{decision.outcome}"
                self._open_positions.discard(key)
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
                await self.memory.add_trade(order)
                self.risk_manager.record_trade(-order.size, order.price)
                # Remove from tracked positions
                key = f"{decision.market_id}:{decision.outcome}"
                self._open_positions.discard(key)
                logger.info(
                    f"[{self.name}] ✅ SELL order placed: ${decision.size:.2f} on '{market_name}'"
                )
                # Send trade alert
                try:
                    alerter = get_alerter()
                    await alerter.alert_trade_executed(
                        market=market_name,
                        side="SELL",
                        size=order.size,
                        price=order.price,
                    )
                except Exception:
                    pass
                return True

            return False

        else:
            logger.warning(f"Unknown action: {decision.action}")
            return False

    async def run_loop(self) -> None:
        """
        Main agent loop: observe → decide → act.

        Runs continuously until stopped. Includes error recovery
        with exponential backoff on repeated failures.
        """
        logger.info(f"[{self.name}] Starting agent loop (interval: {self.loop_interval}s)")
        self.running = True

        # Send bot started alert
        alerter = get_alerter()
        try:
            await alerter.alert_bot_started(
                agent_name=self.name,
                capital=self.risk_manager.current_capital,
            )
        except Exception as e:
            logger.warning(f"Failed to send bot started alert: {e}")

        # Get config values for error recovery
        cfg = get_config()

        # Error tracking for recovery
        self._error_count = 0
        self._consecutive_errors = 0
        self._loop_count = 0
        self._max_consecutive_errors = cfg.agent.max_consecutive_errors
        self._base_backoff = cfg.agent.base_backoff
        self._max_backoff = cfg.agent.max_backoff

        # Try to get recovery manager
        recovery_manager = None
        try:
            from probablyprofit.utils.recovery import get_recovery_manager

            recovery_manager = get_recovery_manager()
        except ImportError:
            pass

        try:
            while self.running:
                self._loop_count += 1

                # Check kill switch before each iteration
                if is_kill_switch_active():
                    reason = get_kill_switch().get_reason() or "Unknown"
                    logger.warning(f"[{self.name}] Kill switch active: {reason}. Stopping agent.")
                    try:
                        await alerter.critical(
                            "Kill Switch Activated",
                            f"Agent {self.name} stopped.\nReason: {reason}",
                        )
                    except Exception:
                        pass
                    self.running = False
                    break

                try:
                    # Observe
                    observation = await self.observe()

                    # Decide
                    decision = await self.decide(observation)

                    # Act
                    success = await self.act(decision)

                    if success:
                        logger.info(
                            f"[{self.name}] Loop iteration {self._loop_count} completed successfully"
                        )
                        self._consecutive_errors = 0  # Reset on success
                    else:
                        logger.warning(f"[{self.name}] Loop iteration {self._loop_count} failed")
                        self._consecutive_errors += 1

                    # Checkpoint periodically
                    if recovery_manager and self._loop_count % cfg.agent.checkpoint_interval == 0:
                        await recovery_manager.checkpoint(self)

                    # Save risk state periodically
                    if self._loop_count % cfg.agent.risk_save_interval == 0 and hasattr(
                        self.risk_manager, "save_state"
                    ):
                        await self.risk_manager.save_state(agent_name=self.name)

                except Exception as e:
                    self._error_count += 1
                    self._consecutive_errors += 1
                    logger.error(
                        f"[{self.name}] Error in loop iteration {self._loop_count}: {e} "
                        f"(consecutive: {self._consecutive_errors})"
                    )

                    # Send error alert
                    try:
                        await alerter.alert_error(
                            error_type=type(e).__name__,
                            error_message=f"Agent: {self.name}\nLoop: {self._loop_count}\n{str(e)[:200]}",
                        )
                    except Exception:
                        pass

                    # Checkpoint on error
                    if recovery_manager:
                        await recovery_manager.checkpoint(self, force=True, error=e)

                    # Check if we should stop
                    if self._consecutive_errors >= self._max_consecutive_errors:
                        logger.critical(
                            f"[{self.name}] Too many consecutive errors ({self._consecutive_errors}). "
                            f"Stopping agent to prevent further issues."
                        )
                        try:
                            await alerter.critical(
                                "Agent Halted - Too Many Errors",
                                f"Agent {self.name} stopped after {self._consecutive_errors} consecutive errors.",
                            )
                        except Exception:
                            pass
                        self.running = False
                        break

                    # Exponential backoff on errors
                    backoff = min(
                        self._base_backoff * (2 ** (self._consecutive_errors - 1)),
                        self._max_backoff,
                    )
                    logger.warning(f"[{self.name}] Backing off for {backoff:.1f}s before retry...")
                    await asyncio.sleep(backoff)
                    continue  # Skip normal sleep, we already waited

                # Wait before next iteration, but check for stop signal
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=self.loop_interval)
                    # If we get here, stop was requested
                    logger.info(f"[{self.name}] Stop signal received")
                    break
                except asyncio.TimeoutError:
                    # Normal timeout, continue loop
                    pass

        except asyncio.CancelledError:
            logger.info(f"[{self.name}] Agent loop cancelled")
        finally:
            # Graceful shutdown cleanup
            await self._cleanup()
            self._running = False

            # Final checkpoint on shutdown
            if recovery_manager:
                await recovery_manager.checkpoint(self, force=True)

    async def _cleanup(self) -> None:
        """Perform graceful shutdown cleanup."""
        logger.info(f"[{self.name}] Performing cleanup...")

        # Send bot stopped alert
        try:
            alerter = get_alerter()
            await alerter.alert_bot_stopped(
                agent_name=self.name,
                reason="Graceful shutdown",
                final_capital=self.risk_manager.current_capital,
            )
        except Exception as e:
            logger.warning(f"Failed to send bot stopped alert: {e}")

        try:
            # Save risk manager state for crash recovery
            if hasattr(self.risk_manager, "save_state"):
                await self.risk_manager.save_state(agent_name=self.name)
                logger.debug(f"[{self.name}] Risk state saved")
        except Exception as e:
            logger.warning(f"[{self.name}] Error saving risk state: {e}")

        try:
            # Close the API client connection
            if hasattr(self.client, "close"):
                await self.client.close()
                logger.debug(f"[{self.name}] API client closed")
        except Exception as e:
            logger.warning(f"[{self.name}] Error closing API client: {e}")

        try:
            # Flush any pending database writes
            if self.memory.enable_persistence and self.memory._db_manager:
                # Give pending writes a chance to complete
                await asyncio.sleep(0.1)
                logger.debug(f"[{self.name}] Database writes flushed")
        except Exception as e:
            logger.warning(f"[{self.name}] Error flushing database: {e}")

        logger.info(f"[{self.name}] Cleanup complete")

    def stop(self) -> None:
        """Stop the agent loop gracefully."""
        logger.info(f"[{self.name}] Stopping agent...")
        self._stop_event.set()

    async def stop_async(self) -> None:
        """Stop the agent loop and wait for cleanup (async version)."""
        logger.info(f"[{self.name}] Stopping agent (async)...")
        self._stop_event.set()
        # Give the loop a moment to exit gracefully
        await asyncio.sleep(0.2)

    def get_health_status(self) -> Dict[str, Any]:
        """Get agent health status."""
        return {
            "name": self.name,
            "running": self.running,
            "loop_count": getattr(self, "_loop_count", 0),
            "error_count": getattr(self, "_error_count", 0),
            "consecutive_errors": getattr(self, "_consecutive_errors", 0),
            "dry_run": self.dry_run,
            "observations": len(self.memory.observations),
            "decisions": len(self.memory.decisions),
            "trades": len(self.memory.trades),
        }

    async def run(self) -> None:
        """
        Convenience method to run the agent.

        Usage:
            agent = MyAgent(client, risk_manager)
            await agent.run()
        """
        await self.run_loop()
