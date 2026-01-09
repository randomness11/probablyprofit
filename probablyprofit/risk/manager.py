"""
Risk Manager

Provides risk management primitives for safe trading.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from loguru import logger
from pydantic import BaseModel


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
        """
        self.limits = limits or RiskLimits()
        self.initial_capital = initial_capital
        self.current_capital = initial_capital

        # Tracking
        self.trades: List[Trade] = []
        self.daily_pnl = 0.0
        self.current_exposure = 0.0
        self.open_positions: Dict[str, float] = {}

        logger.info(f"Risk manager initialized with ${initial_capital:,.2f} capital")
        logger.info(f"Limits: {self.limits}")

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
            logger.warning(
                f"Already at max positions ({self.limits.max_positions})"
            )
            return False

        # Check daily loss limit
        if abs(self.daily_pnl) >= self.limits.max_daily_loss:
            logger.warning(
                f"Daily loss ${abs(self.daily_pnl):.2f} exceeds max "
                f"${self.limits.max_daily_loss:.2f} - trading halted"
            )
            return False

        # Check capital
        if position_value > self.current_capital * 0.5:
            logger.warning(
                f"Position ${position_value:.2f} is >50% of capital "
                f"${self.current_capital:.2f}"
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
            method: Sizing method ("fixed_pct", "kelly", "confidence_based")
            **kwargs: Extra args for methods (e.g. kelly_fraction)

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

        else:
            # Default to fixed percentage
            position_value = self.current_capital * self.limits.position_size_pct
            size = position_value / price

        # Apply max position size limit
        max_size = self.limits.max_position_size / price
        size = min(size, max_size)

        logger.debug(
            f"Position size calculated: {size:.2f} shares "
            f"(${size * price:.2f}) using {method}"
        )

        return size

    def should_stop_loss(
        self,
        entry_price: float,
        current_price: float,
        size: float,
        stop_loss_pct: float = 0.20,
    ) -> bool:
        """
        Check if stop-loss should be triggered.

        Args:
            entry_price: Entry price
            current_price: Current price
            size: Position size
            stop_loss_pct: Stop-loss threshold (default 20%)

        Returns:
            True if stop-loss should trigger
        """
        pnl = size * (current_price - entry_price)
        loss_pct = abs(pnl) / (size * entry_price)

        if pnl < 0 and loss_pct >= stop_loss_pct:
            logger.warning(
                f"Stop-loss triggered: {loss_pct:.1%} loss "
                f"(${pnl:.2f})"
            )
            return True

        return False

    def should_take_profit(
        self,
        entry_price: float,
        current_price: float,
        size: float,
        take_profit_pct: float = 0.50,
    ) -> bool:
        """
        Check if take-profit should be triggered.

        Args:
            entry_price: Entry price
            current_price: Current price
            size: Position size
            take_profit_pct: Take-profit threshold (default 50%)

        Returns:
            True if take-profit should trigger
        """
        pnl = size * (current_price - entry_price)
        profit_pct = pnl / (size * entry_price)

        if pnl > 0 and profit_pct >= take_profit_pct:
            logger.info(
                f"Take-profit triggered: {profit_pct:.1%} profit "
                f"(${pnl:.2f})"
            )
            return True

        return False

    def record_trade(
        self,
        size: float,
        price: float,
        pnl: float = 0.0,
    ) -> None:
        """
        Record a trade.

        Args:
            size: Trade size (positive for buy, negative for sell)
            price: Execution price
            pnl: Realized P&L
        """
        import time

        trade = Trade(
            size=size,
            price=price,
            timestamp=time.time(),
            pnl=pnl,
        )

        self.trades.append(trade)
        self.current_exposure += abs(size * price)
        self.current_capital += pnl
        self.daily_pnl += pnl

        logger.info(
            f"Trade recorded: {size:+.2f} shares @ ${price:.4f} "
            f"(P&L: ${pnl:+.2f})"
        )

    def update_position(
        self,
        market_id: str,
        size: float,
    ) -> None:
        """
        Update position tracking.

        Args:
            market_id: Market identifier
            size: Position size (0 to close)
        """
        if size == 0:
            if market_id in self.open_positions:
                del self.open_positions[market_id]
        else:
            self.open_positions[market_id] = size

    def reset_daily_stats(self) -> None:
        """Reset daily statistics."""
        self.daily_pnl = 0.0
        logger.info("Daily statistics reset")

    def get_stats(self) -> Dict[str, float]:
        """
        Get risk statistics.

        Returns:
            Dictionary of risk metrics
        """
        total_trades = len(self.trades)
        winning_trades = sum(1 for t in self.trades if t.pnl > 0)
        total_pnl = sum(t.pnl for t in self.trades)

        return {
            "current_capital": self.current_capital,
            "total_pnl": total_pnl,
            "daily_pnl": self.daily_pnl,
            "current_exposure": self.current_exposure,
            "open_positions": len(self.open_positions),
            "total_trades": total_trades,
            "win_rate": winning_trades / total_trades if total_trades > 0 else 0.0,
            "return_pct": (self.current_capital - self.initial_capital) / self.initial_capital,
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
