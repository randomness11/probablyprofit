"""
Position Monitor

Automatically monitors open positions and executes stop-loss/take-profit orders.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any
from loguru import logger

from probablyprofit.api.client import PolymarketClient, Position
from probablyprofit.risk.manager import RiskManager


@dataclass
class PositionAlert:
    """An alert for a position event."""
    position_id: str
    market_id: str
    outcome: str
    alert_type: str  # "stop_loss", "take_profit", "warning"
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    executed: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MonitoredPosition:
    """A position being monitored with its thresholds."""
    market_id: str
    outcome: str
    entry_price: float
    size: float
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    trailing_stop_pct: Optional[float] = None
    highest_price: float = 0.0  # For trailing stops
    alerts: List[PositionAlert] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)


class PositionMonitor:
    """
    Monitors positions and automatically executes stop-loss/take-profit.

    Features:
    - Configurable stop-loss and take-profit levels
    - Trailing stop-loss support
    - Alert callbacks for notifications
    - Automatic order execution
    - Health monitoring

    Usage:
        monitor = PositionMonitor(client, risk_manager)

        # Add a position to monitor
        monitor.add_position(
            market_id="0x123",
            outcome="Yes",
            entry_price=0.50,
            size=100,
            stop_loss_pct=0.20,
            take_profit_pct=0.50,
        )

        # Start monitoring
        await monitor.start()
    """

    def __init__(
        self,
        client: PolymarketClient,
        risk_manager: RiskManager,
        check_interval: float = 10.0,
        dry_run: bool = True,
        on_alert: Optional[Callable[[PositionAlert], None]] = None,
    ):
        """
        Initialize position monitor.

        Args:
            client: Polymarket API client
            risk_manager: Risk management system
            check_interval: Seconds between position checks
            dry_run: If True, don't execute real orders
            on_alert: Callback for position alerts
        """
        self.client = client
        self.risk_manager = risk_manager
        self.check_interval = check_interval
        self.dry_run = dry_run
        self.on_alert = on_alert

        self._positions: Dict[str, MonitoredPosition] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # Statistics
        self._checks = 0
        self._stop_losses_triggered = 0
        self._take_profits_triggered = 0
        self._alerts: List[PositionAlert] = []

        logger.info(f"PositionMonitor initialized (interval: {check_interval}s, dry_run: {dry_run})")

    def add_position(
        self,
        market_id: str,
        outcome: str,
        entry_price: float,
        size: float,
        stop_loss_pct: Optional[float] = 0.20,
        take_profit_pct: Optional[float] = 0.50,
        trailing_stop_pct: Optional[float] = None,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
    ) -> str:
        """
        Add a position to monitor.

        Args:
            market_id: Market condition ID
            outcome: Outcome name
            entry_price: Entry price
            size: Position size
            stop_loss_pct: Stop-loss percentage (default 20%)
            take_profit_pct: Take-profit percentage (default 50%)
            trailing_stop_pct: Trailing stop percentage (optional)
            stop_loss_price: Explicit stop-loss price (overrides pct)
            take_profit_price: Explicit take-profit price (overrides pct)

        Returns:
            Position ID
        """
        position_id = f"{market_id}:{outcome}"

        # Calculate prices from percentages if not explicitly set
        if stop_loss_price is None and stop_loss_pct is not None:
            stop_loss_price = entry_price * (1 - stop_loss_pct)

        if take_profit_price is None and take_profit_pct is not None:
            take_profit_price = entry_price * (1 + take_profit_pct)

        position = MonitoredPosition(
            market_id=market_id,
            outcome=outcome,
            entry_price=entry_price,
            size=size,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            trailing_stop_pct=trailing_stop_pct,
            highest_price=entry_price,
        )

        self._positions[position_id] = position

        logger.info(
            f"[PositionMonitor] Added position {position_id}: "
            f"entry={entry_price:.4f}, SL={stop_loss_price:.4f if stop_loss_price else 'None'}, "
            f"TP={take_profit_price:.4f if take_profit_price else 'None'}"
        )

        return position_id

    def remove_position(self, position_id: str) -> bool:
        """Remove a position from monitoring."""
        if position_id in self._positions:
            del self._positions[position_id]
            logger.info(f"[PositionMonitor] Removed position {position_id}")
            return True
        return False

    def update_thresholds(
        self,
        position_id: str,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
        trailing_stop_pct: Optional[float] = None,
    ) -> bool:
        """Update thresholds for a monitored position."""
        if position_id not in self._positions:
            return False

        position = self._positions[position_id]

        if stop_loss_price is not None:
            position.stop_loss_price = stop_loss_price
        if take_profit_price is not None:
            position.take_profit_price = take_profit_price
        if trailing_stop_pct is not None:
            position.trailing_stop_pct = trailing_stop_pct

        logger.info(f"[PositionMonitor] Updated thresholds for {position_id}")
        return True

    async def check_positions(self) -> List[PositionAlert]:
        """
        Check all monitored positions and trigger alerts/orders.

        Returns:
            List of alerts generated
        """
        alerts = []
        self._checks += 1

        # Fetch current positions from API
        try:
            api_positions = await self.client.get_positions()
            position_prices = {
                f"{p.market_id}:{p.outcome}": p.current_price
                for p in api_positions
            }
        except Exception as e:
            logger.warning(f"[PositionMonitor] Failed to fetch positions: {e}")
            return alerts

        for position_id, position in list(self._positions.items()):
            current_price = position_prices.get(position_id)

            if current_price is None:
                # Try to get price from market data
                try:
                    market = await self.client.get_market(position.market_id)
                    if market:
                        idx = market.outcomes.index(position.outcome)
                        current_price = market.outcome_prices[idx]
                except Exception:
                    continue

            if current_price is None:
                continue

            # Update trailing stop high-water mark
            if current_price > position.highest_price:
                position.highest_price = current_price

                # Update trailing stop price
                if position.trailing_stop_pct:
                    position.stop_loss_price = current_price * (1 - position.trailing_stop_pct)

            # Check stop-loss
            if position.stop_loss_price and current_price <= position.stop_loss_price:
                alert = await self._trigger_stop_loss(position, current_price)
                alerts.append(alert)
                self._stop_losses_triggered += 1

            # Check take-profit
            elif position.take_profit_price and current_price >= position.take_profit_price:
                alert = await self._trigger_take_profit(position, current_price)
                alerts.append(alert)
                self._take_profits_triggered += 1

        return alerts

    async def _trigger_stop_loss(
        self,
        position: MonitoredPosition,
        current_price: float,
    ) -> PositionAlert:
        """Trigger a stop-loss order."""
        position_id = f"{position.market_id}:{position.outcome}"

        pnl = position.size * (current_price - position.entry_price)
        pnl_pct = (current_price - position.entry_price) / position.entry_price * 100

        alert = PositionAlert(
            position_id=position_id,
            market_id=position.market_id,
            outcome=position.outcome,
            alert_type="stop_loss",
            message=f"Stop-loss triggered: {pnl_pct:.1f}% loss (${pnl:.2f})",
            metadata={
                "entry_price": position.entry_price,
                "current_price": current_price,
                "stop_loss_price": position.stop_loss_price,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
            }
        )

        logger.warning(f"[PositionMonitor] 🛑 STOP-LOSS: {position_id} @ {current_price:.4f}")

        if not self.dry_run:
            try:
                order = await self.client.place_order(
                    market_id=position.market_id,
                    outcome=position.outcome,
                    side="SELL",
                    size=position.size,
                    price=current_price,
                )
                if order:
                    alert.executed = True
                    self.risk_manager.record_trade(-position.size, current_price, pnl)
                    self.remove_position(position_id)
            except Exception as e:
                logger.error(f"[PositionMonitor] Failed to execute stop-loss: {e}")
        else:
            logger.info(f"[PositionMonitor] DRY RUN: Would sell {position.size} @ {current_price:.4f}")
            self.remove_position(position_id)

        self._alerts.append(alert)
        position.alerts.append(alert)

        if self.on_alert:
            self.on_alert(alert)

        return alert

    async def _trigger_take_profit(
        self,
        position: MonitoredPosition,
        current_price: float,
    ) -> PositionAlert:
        """Trigger a take-profit order."""
        position_id = f"{position.market_id}:{position.outcome}"

        pnl = position.size * (current_price - position.entry_price)
        pnl_pct = (current_price - position.entry_price) / position.entry_price * 100

        alert = PositionAlert(
            position_id=position_id,
            market_id=position.market_id,
            outcome=position.outcome,
            alert_type="take_profit",
            message=f"Take-profit triggered: +{pnl_pct:.1f}% profit (${pnl:.2f})",
            metadata={
                "entry_price": position.entry_price,
                "current_price": current_price,
                "take_profit_price": position.take_profit_price,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
            }
        )

        logger.info(f"[PositionMonitor] 🎯 TAKE-PROFIT: {position_id} @ {current_price:.4f}")

        if not self.dry_run:
            try:
                order = await self.client.place_order(
                    market_id=position.market_id,
                    outcome=position.outcome,
                    side="SELL",
                    size=position.size,
                    price=current_price,
                )
                if order:
                    alert.executed = True
                    self.risk_manager.record_trade(-position.size, current_price, pnl)
                    self.remove_position(position_id)
            except Exception as e:
                logger.error(f"[PositionMonitor] Failed to execute take-profit: {e}")
        else:
            logger.info(f"[PositionMonitor] DRY RUN: Would sell {position.size} @ {current_price:.4f}")
            self.remove_position(position_id)

        self._alerts.append(alert)
        position.alerts.append(alert)

        if self.on_alert:
            self.on_alert(alert)

        return alert

    async def start(self) -> None:
        """Start the position monitoring loop."""
        if self._running:
            logger.warning("[PositionMonitor] Already running")
            return

        self._running = True
        logger.info("[PositionMonitor] Starting position monitoring...")

        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Stop the position monitoring loop."""
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("[PositionMonitor] Stopped")

    async def _run_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                await self.check_positions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[PositionMonitor] Error in monitoring loop: {e}")

            await asyncio.sleep(self.check_interval)

    @property
    def positions(self) -> Dict[str, MonitoredPosition]:
        """Get all monitored positions."""
        return self._positions.copy()

    @property
    def stats(self) -> Dict[str, Any]:
        """Get monitoring statistics."""
        return {
            "running": self._running,
            "positions_monitored": len(self._positions),
            "total_checks": self._checks,
            "stop_losses_triggered": self._stop_losses_triggered,
            "take_profits_triggered": self._take_profits_triggered,
            "total_alerts": len(self._alerts),
            "dry_run": self.dry_run,
        }

    def get_recent_alerts(self, n: int = 10) -> List[PositionAlert]:
        """Get the most recent alerts."""
        return self._alerts[-n:]


async def create_position_monitor(
    client: PolymarketClient,
    risk_manager: RiskManager,
    dry_run: bool = True,
    auto_start: bool = True,
) -> PositionMonitor:
    """
    Factory function to create and optionally start a position monitor.

    Args:
        client: Polymarket client
        risk_manager: Risk manager
        dry_run: Dry run mode
        auto_start: Start monitoring immediately

    Returns:
        Configured PositionMonitor
    """
    monitor = PositionMonitor(
        client=client,
        risk_manager=risk_manager,
        dry_run=dry_run,
    )

    if auto_start:
        await monitor.start()

    return monitor
