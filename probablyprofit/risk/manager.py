"""
Risk Manager

Provides risk management primitives for safe trading.

# TODO: Large file refactoring (857 lines) - consider splitting into:
# - risk/sizing.py - Position sizing methods (kelly_size, calculate_position_size, _dynamic_size)
# - risk/alerts.py - Alert scheduling and sending (_schedule_drawdown_alert, _send_daily_loss_alert)
# - risk/persistence.py - State save/load, serialization (save_state, load_state, to_dict, from_dict)
# - risk/limits.py - RiskLimits model and validation
# - risk/tracking.py - Trade tracking, drawdown calculation, exposure management
"""

import asyncio
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from loguru import logger
from pydantic import BaseModel

from probablyprofit.alerts.telegram import get_alerter
from probablyprofit.config import get_config


class RiskLimits(BaseModel):
    """Risk limit configuration."""

    max_position_size: float = 100.0  # Max size per position in USD
    max_total_exposure: float = 1000.0  # Max total exposure in USD
    max_positions: int = 10  # Max number of open positions
    max_loss_per_trade: float = 50.0  # Max loss per trade in USD
    max_daily_loss: float = 200.0  # Max daily loss in USD
    min_liquidity: float = 100.0  # Min market liquidity in USD
    max_price_impact: float = 0.05  # Max acceptable price impact (5%)
    position_size_pct: float = 0.05  # Default position size as % of capital


@dataclass
class Trade:
    """Trade record."""

    size: float
    price: float
    timestamp: float
    pnl: float = 0.0


class RiskManager:
    """
    Risk management system.

    Enforces position limits, stop-losses, and portfolio constraints
    to prevent excessive risk-taking.

    Features:
    - Position sizing (Kelly criterion, fixed %, etc.)
    - Stop-loss / take-profit levels
    - Maximum exposure limits
    - Daily loss limits
    - Liquidity checks
    """

    def __init__(
        self,
        limits: Optional[RiskLimits] = None,
        initial_capital: float = 1000.0,
    ):
        """
        Initialize risk manager.

        Args:
            limits: Risk limits configuration
            initial_capital: Starting capital in USD

        Raises:
            ValueError: If initial_capital or limits have invalid values
        """
        self.limits = limits or RiskLimits()

        # Validate to prevent division by zero
        if initial_capital <= 0:
            raise ValueError(f"initial_capital must be positive, got {initial_capital}")
        if self.limits.max_daily_loss <= 0:
            raise ValueError(f"max_daily_loss must be positive, got {self.limits.max_daily_loss}")

        self.initial_capital = initial_capital
        self.current_capital = initial_capital

        # Tracking
        self.trades: List[Trade] = []
        self.daily_pnl = 0.0
        self.current_exposure = 0.0
        self.open_positions: Dict[str, float] = {}  # market_id -> (size, entry_price)
        self.position_prices: Dict[str, float] = {}  # market_id -> entry_price

        # Drawdown tracking
        self.peak_capital = initial_capital
        self.max_drawdown_pct = get_config().risk.max_drawdown_pct
        self._drawdown_halt = False  # Flag to halt trading on max drawdown

        # Thread-safe locks for state modification
        self._state_lock = threading.Lock()
        self._async_lock: Optional[asyncio.Lock] = None

        logger.info(f"Risk manager initialized with ${initial_capital:,.2f} capital")
        logger.info(f"Limits: {self.limits}")
        logger.info(f"Max drawdown limit: {self.max_drawdown_pct:.0%}")

    def _get_async_lock(self) -> asyncio.Lock:
        """Get or create async lock (lazy init for event loop compatibility)."""
        if self._async_lock is None:
            self._async_lock = asyncio.Lock()
        return self._async_lock

    def recalculate_exposure(self) -> float:
        """
        Recalculate total exposure from open positions.

        This fixes the bug where exposure only increases and never decreases.
        Should be called after positions are closed.

        Returns:
            Updated current exposure value
        """
        with self._state_lock:
            total_exposure = 0.0
            for market_id, size in self.open_positions.items():
                price = self.position_prices.get(market_id, 0.5)  # Default to 0.5 if no price
                total_exposure += abs(size * price)
            self.current_exposure = total_exposure
            return total_exposure

    def get_current_drawdown(self) -> float:
        """
        Calculate current drawdown from peak capital.

        Returns:
            Drawdown as a percentage (0.0 to 1.0)
        """
        if self.peak_capital <= 0:
            return 0.0
        return (self.peak_capital - self.current_capital) / self.peak_capital

    def update_peak_capital(self) -> None:
        """Update peak capital if current capital is higher."""
        with self._state_lock:
            if self.current_capital > self.peak_capital:
                self.peak_capital = self.current_capital
                logger.debug(f"New peak capital: ${self.peak_capital:,.2f}")

    def check_drawdown_limit(self) -> bool:
        """
        Check if max drawdown limit has been exceeded.

        Returns:
            True if drawdown exceeds limit (trading should halt)
        """
        drawdown = self.get_current_drawdown()
        if drawdown >= self.max_drawdown_pct:
            if not self._drawdown_halt:
                self._drawdown_halt = True
                logger.error(
                    f"MAX DRAWDOWN EXCEEDED: {drawdown:.1%} >= {self.max_drawdown_pct:.1%}. "
                    f"Trading halted. Peak: ${self.peak_capital:,.2f}, "
                    f"Current: ${self.current_capital:,.2f}"
                )
                # Send Telegram alert (fire and forget)
                self._schedule_drawdown_alert(drawdown)
            return True
        return False

    def _schedule_drawdown_alert(self, drawdown: float) -> None:
        """Schedule async alert for max drawdown exceeded."""
        try:
            # Try to get the running loop (Python 3.10+ safe)
            loop = asyncio.get_running_loop()
            loop.create_task(self._send_drawdown_alert(drawdown))
        except RuntimeError:
            # No running event loop - alerts are non-critical, just log
            logger.debug("Could not send drawdown alert - no running event loop")

    async def _send_drawdown_alert(self, drawdown: float) -> None:
        """Send max drawdown exceeded alert."""
        try:
            alerter = get_alerter()
            await alerter.alert_max_drawdown_exceeded(
                drawdown_pct=drawdown,
                peak_capital=self.peak_capital,
                current_capital=self.current_capital,
            )
        except Exception as e:
            logger.warning(f"Failed to send drawdown alert: {e}")

    def _schedule_daily_loss_alert(self, exceeded: bool, pct: float = 1.0) -> None:
        """Schedule async alert for daily loss limit."""
        try:
            # Try to get the running loop (Python 3.10+ safe)
            loop = asyncio.get_running_loop()
            loop.create_task(self._send_daily_loss_alert(exceeded, pct))
        except RuntimeError:
            # No running event loop - alerts are non-critical, just log
            logger.debug("Could not send daily loss alert - no running event loop")

    async def _send_daily_loss_alert(self, exceeded: bool, pct: float) -> None:
        """Send daily loss limit alert."""
        try:
            alerter = get_alerter()
            if exceeded:
                await alerter.alert_daily_loss_exceeded(
                    current_loss=self.daily_pnl,
                    max_loss=self.limits.max_daily_loss,
                )
            else:
                await alerter.alert_daily_loss_approaching(
                    current_loss=self.daily_pnl,
                    max_loss=self.limits.max_daily_loss,
                    pct=pct,
                )
        except Exception as e:
            logger.warning(f"Failed to send daily loss alert: {e}")

    def reset_drawdown_halt(self) -> None:
        """Reset the drawdown halt flag (use with caution)."""
        with self._state_lock:
            self._drawdown_halt = False
            logger.warning("Drawdown halt flag reset manually")

    def can_open_position(
        self,
        size: float,
        price: float,
        market_id: Optional[str] = None,
    ) -> bool:
        """
        Check if a position can be opened within risk limits.

        Args:
            size: Position size in shares
            price: Entry price
            market_id: Market identifier

        Returns:
            True if position is within risk limits
        """
        # Check drawdown halt first
        if self._drawdown_halt or self.check_drawdown_limit():
            logger.warning("Trading halted due to max drawdown limit")
            return False

        position_value = size * price

        # Check position size limit
        if position_value > self.limits.max_position_size:
            logger.warning(
                f"Position size ${position_value:.2f} exceeds max "
                f"${self.limits.max_position_size:.2f}"
            )
            return False

        # Check total exposure limit
        new_exposure = self.current_exposure + position_value
        if new_exposure > self.limits.max_total_exposure:
            logger.warning(
                f"Total exposure ${new_exposure:.2f} would exceed max "
                f"${self.limits.max_total_exposure:.2f}"
            )
            return False

        # Check max positions
        if len(self.open_positions) >= self.limits.max_positions:
            logger.warning(f"Already at max positions ({self.limits.max_positions})")
            return False

        # Check daily loss limit
        if abs(self.daily_pnl) >= self.limits.max_daily_loss:
            logger.warning(
                f"Daily loss ${abs(self.daily_pnl):.2f} exceeds max "
                f"${self.limits.max_daily_loss:.2f} - trading halted"
            )
            # Send alert for daily loss exceeded
            self._schedule_daily_loss_alert(exceeded=True)
            return False

        # Warn if approaching daily loss limit (>80% used)
        daily_loss_pct = abs(self.daily_pnl) / self.limits.max_daily_loss
        if daily_loss_pct >= 0.8 and not getattr(self, "_daily_loss_warned", False):
            self._daily_loss_warned = True
            self._schedule_daily_loss_alert(exceeded=False, pct=daily_loss_pct)

        # Check capital
        if position_value > self.current_capital * 0.5:
            logger.warning(
                f"Position ${position_value:.2f} is >50% of capital " f"${self.current_capital:.2f}"
            )
            return False

        return True

    def kelly_size(
        self,
        win_prob: float,
        price: float,
        fraction: float = 0.25,
    ) -> float:
        """
        Calculate Kelly criterion position size.

        Args:
            win_prob: Probability of winning (0-1)
            price: Entry price (0-1)
            fraction: Kelly fraction (default 0.25 for Quarter Kelly)

        Returns:
            Position size in shares
        """
        if price <= 0 or price >= 1:
            return 0.0

        # Kelly Formula: f = p - (1-p)/b
        # where b is net odds received = (1-price)/price
        loss_prob = 1 - win_prob
        net_odds = (1 - price) / price

        if net_odds == 0:
            return 0.0

        kelly_pct = win_prob - (loss_prob / net_odds)

        # Apply fractional Kelly (e.g. Quarter Kelly) for safety
        adjusted_pct = kelly_pct * fraction

        # Clamp between 0 and max position size %
        # We also respect the global max_position_size in calculate_position_size
        safe_pct = max(0.0, adjusted_pct)

        position_value = self.current_capital * safe_pct
        size = position_value / price

        return size

    def calculate_position_size(
        self,
        price: float,
        confidence: float = 0.5,
        method: str = "fixed_pct",
        **kwargs,
    ) -> float:
        """
        Calculate appropriate position size.

        Args:
            price: Entry price
            confidence: Confidence level (0-1)
            method: Sizing method ("fixed_pct", "kelly", "confidence_based", "dynamic")
            **kwargs: Extra args for methods (e.g. kelly_fraction, volatility)

        Returns:
            Position size in shares
        """
        if method == "fixed_pct":
            # Fixed percentage of capital
            position_value = self.current_capital * self.limits.position_size_pct
            size = position_value / price

        elif method == "confidence_based":
            # Scale position size with confidence
            base_pct = self.limits.position_size_pct
            adjusted_pct = base_pct * confidence
            position_value = self.current_capital * adjusted_pct
            size = position_value / price

        elif method == "kelly":
            # Kelly criterion
            kelly_fraction = kwargs.get("kelly_fraction", 0.25)
            size = self.kelly_size(confidence, price, fraction=kelly_fraction)

        elif method == "dynamic":
            # Dynamic sizing based on multiple factors
            size = self._dynamic_size(price, confidence, **kwargs)

        else:
            # Default to fixed percentage
            position_value = self.current_capital * self.limits.position_size_pct
            size = position_value / price

        # Apply max position size limit
        max_size = self.limits.max_position_size / price
        size = min(size, max_size)

        logger.debug(
            f"Position size calculated: {size:.2f} shares " f"(${size * price:.2f}) using {method}"
        )

        return size

    def _dynamic_size(
        self,
        price: float,
        confidence: float,
        volatility: float = 0.5,
        win_streak: int = 0,
        lose_streak: int = 0,
        **kwargs,
    ) -> float:
        """
        Dynamic position sizing based on multiple factors.

        Increases size when:
        - High confidence
        - Low volatility
        - On a winning streak

        Decreases size when:
        - Low confidence
        - High volatility
        - On a losing streak
        - Recent losses

        Args:
            price: Entry price
            confidence: AI confidence (0-1)
            volatility: Market volatility (0-1, higher = more volatile)
            win_streak: Number of consecutive wins
            lose_streak: Number of consecutive losses

        Returns:
            Position size in shares
        """
        base_pct = self.limits.position_size_pct

        # Confidence factor (0.5x to 1.5x)
        confidence_factor = 0.5 + confidence

        # Volatility factor (reduce size in volatile markets)
        # Low volatility (0.2) -> 1.2x, High volatility (0.8) -> 0.6x
        volatility_factor = 1.4 - volatility

        # Streak factor
        if win_streak >= 3:
            streak_factor = min(1.3, 1.0 + win_streak * 0.05)  # Up to 1.3x on hot streak
        elif lose_streak >= 2:
            streak_factor = max(0.5, 1.0 - lose_streak * 0.15)  # Down to 0.5x on cold streak
        else:
            streak_factor = 1.0

        # Recent performance factor (reduce if recent losses)
        perf_factor = 1.0
        if self.daily_pnl < 0:
            # Reduce size proportionally to daily losses
            loss_ratio = abs(self.daily_pnl) / self.limits.max_daily_loss
            perf_factor = max(0.5, 1.0 - loss_ratio * 0.5)

        # Capital preservation factor (reduce as capital decreases)
        capital_ratio = self.current_capital / self.initial_capital
        if capital_ratio < 0.8:
            capital_factor = max(0.5, capital_ratio)
        else:
            capital_factor = 1.0

        # Combine all factors
        combined_factor = (
            confidence_factor * volatility_factor * streak_factor * perf_factor * capital_factor
        )

        # Apply to base size
        adjusted_pct = base_pct * combined_factor
        adjusted_pct = max(0.01, min(0.20, adjusted_pct))  # Clamp 1-20%

        position_value = self.current_capital * adjusted_pct
        size = position_value / price

        logger.debug(
            f"Dynamic sizing: base={base_pct:.2%} × "
            f"conf={confidence_factor:.2f} × vol={volatility_factor:.2f} × "
            f"streak={streak_factor:.2f} × perf={perf_factor:.2f} × "
            f"capital={capital_factor:.2f} = {adjusted_pct:.2%}"
        )

        return size

    def should_stop_loss(
        self,
        entry_price: float,
        current_price: float,
        size: float,
        stop_loss_pct: Optional[float] = None,
    ) -> bool:
        """
        Check if stop-loss should be triggered.

        Args:
            entry_price: Entry price
            current_price: Current price
            size: Position size
            stop_loss_pct: Stop-loss threshold (default from config)

        Returns:
            True if stop-loss should trigger
        """
        if stop_loss_pct is None:
            stop_loss_pct = get_config().risk.default_stop_loss_pct

        pnl = size * (current_price - entry_price)
        loss_pct = abs(pnl) / (size * entry_price)

        if pnl < 0 and loss_pct >= stop_loss_pct:
            logger.warning(f"Stop-loss triggered: {loss_pct:.1%} loss " f"(${pnl:.2f})")
            return True

        return False

    def should_take_profit(
        self,
        entry_price: float,
        current_price: float,
        size: float,
        take_profit_pct: Optional[float] = None,
    ) -> bool:
        """
        Check if take-profit should be triggered.

        Args:
            entry_price: Entry price
            current_price: Current price
            size: Position size
            take_profit_pct: Take-profit threshold (default from config)

        Returns:
            True if take-profit should trigger
        """
        if take_profit_pct is None:
            take_profit_pct = get_config().risk.default_take_profit_pct

        pnl = size * (current_price - entry_price)
        profit_pct = pnl / (size * entry_price)

        if pnl > 0 and profit_pct >= take_profit_pct:
            logger.info(f"Take-profit triggered: {profit_pct:.1%} profit " f"(${pnl:.2f})")
            return True

        return False

    def record_trade(
        self,
        size: float,
        price: float,
        pnl: float = 0.0,
        market_id: Optional[str] = None,
    ) -> None:
        """
        Record a trade (thread-safe).

        Args:
            size: Trade size (positive for buy, negative for sell)
            price: Execution price
            pnl: Realized P&L
            market_id: Optional market ID for position tracking
        """
        import time

        trade = Trade(
            size=size,
            price=price,
            timestamp=time.time(),
            pnl=pnl,
        )

        with self._state_lock:
            self.trades.append(trade)
            self.current_capital += pnl
            self.daily_pnl += pnl

        # Update peak capital after profitable trade
        if pnl > 0:
            self.update_peak_capital()

        # Check drawdown after loss
        if pnl < 0:
            self.check_drawdown_limit()

        # Recalculate exposure from actual positions (fixes the accumulation bug)
        self.recalculate_exposure()

        logger.info(f"Trade recorded: {size:+.2f} shares @ ${price:.4f} (P&L: ${pnl:+.2f})")

    def update_position(
        self,
        market_id: str,
        size: float,
        price: Optional[float] = None,
    ) -> None:
        """
        Update position tracking (thread-safe).

        Args:
            market_id: Market identifier
            size: Position size (0 to close)
            price: Entry price for the position
        """
        with self._state_lock:
            if size == 0:
                # Position closed
                if market_id in self.open_positions:
                    del self.open_positions[market_id]
                if market_id in self.position_prices:
                    del self.position_prices[market_id]
            else:
                # Position opened/updated
                self.open_positions[market_id] = size
                if price is not None:
                    self.position_prices[market_id] = price

        # Recalculate exposure after position change
        self.recalculate_exposure()

    def reset_daily_stats(self) -> None:
        """Reset daily statistics (thread-safe)."""
        with self._state_lock:
            self.daily_pnl = 0.0
            self._daily_loss_warned = False
        logger.info("Daily statistics reset")

    def get_stats(self) -> Dict[str, float]:
        """
        Get risk statistics (thread-safe).

        Returns:
            Dictionary of risk metrics
        """
        with self._state_lock:
            total_trades = len(self.trades)
            winning_trades = sum(1 for t in self.trades if t.pnl > 0)
            total_pnl = sum(t.pnl for t in self.trades)
            current_drawdown = self.get_current_drawdown()

            return {
                "current_capital": self.current_capital,
                "initial_capital": self.initial_capital,
                "peak_capital": self.peak_capital,
                "total_pnl": total_pnl,
                "daily_pnl": self.daily_pnl,
                "current_exposure": self.current_exposure,
                "open_positions": len(self.open_positions),
                "total_trades": total_trades,
                "win_rate": winning_trades / total_trades if total_trades > 0 else 0.0,
                "return_pct": (self.current_capital - self.initial_capital) / self.initial_capital,
                "current_drawdown": current_drawdown,
                "max_drawdown_limit": self.max_drawdown_pct,
                "drawdown_halt": self._drawdown_halt,
            }

    def __repr__(self) -> str:
        """String representation."""
        stats = self.get_stats()
        return (
            f"RiskManager("
            f"capital=${stats['current_capital']:.2f}, "
            f"pnl=${stats['total_pnl']:+.2f}, "
            f"positions={stats['open_positions']}, "
            f"win_rate={stats['win_rate']:.1%})"
        )

    # =========================================================================
    # PERSISTENCE METHODS
    # =========================================================================

    async def save_state(self, agent_name: str = "unknown") -> bool:
        """
        Persist current risk state to database for crash recovery.

        Args:
            agent_name: Name of the agent for identification

        Returns:
            True if save succeeded
        """
        import json

        try:
            from sqlmodel import select

            from probablyprofit.storage.database import get_db_manager
            from probablyprofit.storage.models import RiskStateRecord

            db = get_db_manager()

            with self._state_lock:
                # Serialize trades to JSON
                trades_data = [
                    {
                        "size": t.size,
                        "price": t.price,
                        "timestamp": t.timestamp,
                        "pnl": t.pnl,
                    }
                    for t in self.trades[-100:]  # Keep last 100 trades
                ]

                state_record = RiskStateRecord(
                    initial_capital=self.initial_capital,
                    current_capital=self.current_capital,
                    current_exposure=self.current_exposure,
                    daily_pnl=self.daily_pnl,
                    open_positions_json=json.dumps(self.open_positions),
                    trades_json=json.dumps(trades_data),
                    agent_name=agent_name,
                    is_latest=True,
                )

            async with db.get_session() as session:
                # Mark all previous records as not latest
                stmt = select(RiskStateRecord).where(
                    RiskStateRecord.agent_name == agent_name, RiskStateRecord.is_latest == True
                )
                result = await session.execute(stmt)
                old_records = result.scalars().all()
                for record in old_records:
                    record.is_latest = False

                # Add new record
                session.add(state_record)
                await session.commit()

            logger.debug(f"Risk state saved for agent '{agent_name}'")
            return True

        except (ImportError, ModuleNotFoundError) as e:
            logger.warning(f"Failed to save risk state - missing module: {e}")
            return False
        except OSError as e:
            logger.warning(f"Failed to save risk state - I/O error: {e}")
            return False
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to save risk state - serialization error: {e}")
            return False

    async def load_state(self, agent_name: str = "unknown") -> bool:
        """
        Load risk state from database (for crash recovery).

        Args:
            agent_name: Name of the agent to load state for

        Returns:
            True if state was loaded successfully
        """
        import json

        try:
            from sqlmodel import select

            from probablyprofit.storage.database import get_db_manager
            from probablyprofit.storage.models import RiskStateRecord

            db = get_db_manager()

            async with db.get_session() as session:
                stmt = (
                    select(RiskStateRecord)
                    .where(
                        RiskStateRecord.agent_name == agent_name, RiskStateRecord.is_latest == True
                    )
                    .order_by(RiskStateRecord.timestamp.desc())
                    .limit(1)
                )

                result = await session.execute(stmt)
                record = result.scalar_one_or_none()

                if not record:
                    logger.info(f"No saved risk state found for agent '{agent_name}'")
                    return False

                with self._state_lock:
                    self.initial_capital = record.initial_capital
                    self.current_capital = record.current_capital
                    self.current_exposure = record.current_exposure
                    self.daily_pnl = record.daily_pnl
                    self.open_positions = json.loads(record.open_positions_json)

                    # Restore trades
                    trades_data = json.loads(record.trades_json)
                    self.trades = [
                        Trade(
                            size=t["size"],
                            price=t["price"],
                            timestamp=t["timestamp"],
                            pnl=t["pnl"],
                        )
                        for t in trades_data
                    ]

                logger.info(
                    f"Risk state restored for agent '{agent_name}': "
                    f"capital=${self.current_capital:.2f}, "
                    f"positions={len(self.open_positions)}"
                )
                return True

        except (ImportError, ModuleNotFoundError) as e:
            logger.warning(f"Failed to load risk state - missing module: {e}")
            return False
        except OSError as e:
            logger.warning(f"Failed to load risk state - I/O error: {e}")
            return False
        except (ValueError, TypeError, KeyError) as e:
            logger.warning(f"Failed to load risk state - deserialization error: {e}")
            return False
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to load risk state - invalid JSON: {e}")
            return False

    def to_dict(self) -> Dict[str, Any]:
        """
        Export current state as dictionary (for JSON serialization).

        Returns:
            Dict with all risk state
        """
        with self._state_lock:
            return {
                "initial_capital": self.initial_capital,
                "current_capital": self.current_capital,
                "current_exposure": self.current_exposure,
                "daily_pnl": self.daily_pnl,
                "peak_capital": self.peak_capital,
                "max_drawdown_pct": self.max_drawdown_pct,
                "drawdown_halt": self._drawdown_halt,
                "open_positions": dict(self.open_positions),
                "position_prices": dict(self.position_prices),
                "trades": [
                    {
                        "size": t.size,
                        "price": t.price,
                        "timestamp": t.timestamp,
                        "pnl": t.pnl,
                    }
                    for t in self.trades
                ],
                "limits": self.limits.model_dump(),
            }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RiskManager":
        """
        Create RiskManager from dictionary state.

        Args:
            data: Dict with risk state

        Returns:
            RiskManager instance
        """
        limits = RiskLimits(**data.get("limits", {}))
        manager = cls(
            limits=limits,
            initial_capital=data.get("initial_capital", 1000.0),
        )

        manager.current_capital = data.get("current_capital", manager.initial_capital)
        manager.current_exposure = data.get("current_exposure", 0.0)
        manager.daily_pnl = data.get("daily_pnl", 0.0)
        manager.peak_capital = data.get("peak_capital", manager.initial_capital)
        manager.max_drawdown_pct = data.get("max_drawdown_pct", 0.30)
        manager._drawdown_halt = data.get("drawdown_halt", False)
        manager.open_positions = data.get("open_positions", {})
        manager.position_prices = data.get("position_prices", {})
        manager.trades = [
            Trade(
                size=t["size"],
                price=t["price"],
                timestamp=t["timestamp"],
                pnl=t["pnl"],
            )
            for t in data.get("trades", [])
        ]

        return manager
