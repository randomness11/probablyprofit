"""
Backtest Engine

Simulates trading strategies on historical data.

PERFORMANCE OPTIMIZATION:
    Uses collections.deque with maxlen for bounded equity history
    to prevent memory leaks during long backtests.
"""

import asyncio
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional

import pandas as pd
from loguru import logger
from pydantic import BaseModel

from probablyprofit.agent.base import BaseAgent, Decision, Observation
from probablyprofit.api.client import Market, Order, Position
from probablyprofit.risk.manager import RiskManager

# Default max size for equity history to prevent memory leaks
DEFAULT_EQUITY_HISTORY_MAXLEN = 100_000


class BacktestResult(BaseModel):
    """Backtest results."""

    start_time: datetime
    end_time: datetime
    initial_capital: float
    final_capital: float
    total_return: float
    total_return_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    max_drawdown: float
    sharpe_ratio: float
    trades: List[Dict[str, Any]] = []
    equity_curve: List[Dict[str, Any]] = []


class BacktestEngine:
    """
    Backtesting engine for strategy simulation.

    Features:
    - Historical market data replay
    - Paper trading simulation
    - Performance metrics calculation
    - Strategy comparison
    - PERFORMANCE: Bounded equity history to prevent memory leaks
    """

    def __init__(
        self,
        initial_capital: float = 1000.0,
        equity_history_maxlen: Optional[int] = None,
    ):
        """
        Initialize backtest engine.

        Args:
            initial_capital: Starting capital
            equity_history_maxlen: Max size of equity history (prevents memory leaks).
                                   Set to None for unlimited (use with caution).
                                   Default: 100,000 entries (~10MB memory)
        """
        self.initial_capital = initial_capital
        self.current_capital = initial_capital

        # PERFORMANCE OPTIMIZATION: Set max length for equity history
        # This prevents unbounded memory growth during long backtests
        self._equity_history_maxlen = equity_history_maxlen or DEFAULT_EQUITY_HISTORY_MAXLEN

        # Simulation state
        self.positions: Dict[str, Position] = {}
        self.trades: List[Order] = []

        # PERFORMANCE: Use deque with maxlen for bounded equity history
        # Automatically evicts oldest entries when maxlen is exceeded
        self._equity_history_deque: Deque[Dict[str, Any]] = deque(
            maxlen=self._equity_history_maxlen
        )

        logger.info(
            f"Backtest engine initialized with ${initial_capital:,.2f} "
            f"(equity_history_maxlen={self._equity_history_maxlen})"
        )

    @property
    def equity_history(self) -> List[Dict[str, Any]]:
        """
        Get equity history as a list.

        PERFORMANCE NOTE: This creates a list copy. For large histories,
        consider iterating over _equity_history_deque directly.
        """
        return list(self._equity_history_deque)

    @equity_history.setter
    def equity_history(self, value: List[Dict[str, Any]]) -> None:
        """Set equity history from a list."""
        self._equity_history_deque.clear()
        for item in value:
            self._equity_history_deque.append(item)

    async def run_backtest(
        self,
        agent: BaseAgent,
        market_data: List[List[Market]],
        timestamps: List[datetime],
    ) -> BacktestResult:
        """
        Run a backtest simulation.

        Args:
            agent: Trading agent to test
            market_data: List of market snapshots over time
            timestamps: Corresponding timestamps

        Returns:
            BacktestResult with performance metrics
        """
        logger.info(
            f"Starting backtest: {len(market_data)} snapshots "
            f"from {timestamps[0]} to {timestamps[-1]}"
        )

        self.current_capital = self.initial_capital
        self.positions = {}
        self.trades = []
        # PERFORMANCE: Clear the deque instead of creating new list
        self._equity_history_deque.clear()

        # Simulate trading over time
        for i, (markets, timestamp) in enumerate(zip(market_data, timestamps)):
            logger.debug(f"Simulating {timestamp} ({i+1}/{len(market_data)})")

            # Create observation
            observation = Observation(
                timestamp=timestamp,
                markets=markets,
                positions=list(self.positions.values()),
                balance=self.current_capital,
            )

            # Get agent decision
            decision = await agent.decide(observation)

            # Execute decision in simulation
            self._execute_simulated_trade(decision, markets)

            # Record equity - PERFORMANCE: Use deque.append for O(1) with auto-eviction
            total_equity = self._calculate_total_equity(markets)
            self._equity_history_deque.append(
                {
                    "timestamp": timestamp,
                    "equity": total_equity,
                    "cash": self.current_capital,
                    "positions_value": total_equity - self.current_capital,
                }
            )

        # Calculate final metrics
        result = self._calculate_results(timestamps[0], timestamps[-1])

        logger.info(
            f"Backtest complete: ${result.final_capital:,.2f} "
            f"({result.total_return_pct:+.2%} return)"
        )

        return result

    def _execute_simulated_trade(
        self,
        decision: Decision,
        markets: List[Market],
    ) -> None:
        """
        Execute a trade in simulation.

        Args:
            decision: Trading decision
            markets: Current market data
        """
        if decision.action == "hold":
            return

        # Find the market
        market = next((m for m in markets if m.condition_id == decision.market_id), None)

        if not market:
            return

        if decision.action == "buy":
            # Execute buy
            cost = decision.size * decision.price
            if cost <= self.current_capital:
                self.current_capital -= cost

                # Create position
                position = Position(
                    market_id=decision.market_id,
                    outcome=decision.outcome or market.outcomes[0],
                    size=decision.size,
                    avg_price=decision.price,
                    current_price=decision.price,
                )

                self.positions[decision.market_id] = position

                # Record trade
                trade = Order(
                    market_id=decision.market_id,
                    market_question=market.question,  # For searchable trade history
                    outcome=decision.outcome or market.outcomes[0],
                    side="BUY",
                    size=decision.size,
                    price=decision.price,
                    status="filled",
                )
                self.trades.append(trade)

                logger.debug(f"Executed BUY: {decision.size} @ ${decision.price}")

        elif decision.action == "sell":
            # Execute sell
            if decision.market_id in self.positions:
                position = self.positions[decision.market_id]

                # Calculate P&L
                pnl = position.size * (decision.price - position.avg_price)
                self.current_capital += position.size * decision.price

                # Remove position
                del self.positions[decision.market_id]

                # Record trade
                trade = Order(
                    market_id=decision.market_id,
                    market_question=market.question,  # For searchable trade history
                    outcome=decision.outcome or market.outcomes[0],
                    side="SELL",
                    size=position.size,
                    price=decision.price,
                    status="filled",
                )
                self.trades.append(trade)

                logger.debug(
                    f"Executed SELL: {position.size} @ ${decision.price} (P&L: ${pnl:+.2f})"
                )

    def _calculate_total_equity(
        self,
        markets: List[Market],
    ) -> float:
        """
        Calculate total equity (cash + positions).

        Args:
            markets: Current market data

        Returns:
            Total equity value
        """
        equity = self.current_capital

        for position in self.positions.values():
            # Find current market price
            market = next((m for m in markets if m.condition_id == position.market_id), None)

            if market and market.outcome_prices:
                current_price = market.outcome_prices[0]  # Simplified
                equity += position.size * current_price

        return equity

    def _calculate_results(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> BacktestResult:
        """
        Calculate backtest results and metrics.

        Args:
            start_time: Backtest start time
            end_time: Backtest end time

        Returns:
            BacktestResult object
        """
        # PERFORMANCE: Access deque directly instead of converting to list
        final_capital = (
            self._equity_history_deque[-1]["equity"]
            if self._equity_history_deque
            else self.initial_capital
        )

        from probablyprofit.backtesting.metrics import PerformanceMetrics

        # Prepare data for metrics
        trade_dicts = [
            {
                "market_id": t.market_id,
                "side": t.side,
                "size": t.size,
                "price": t.price,
                "timestamp": getattr(t, "timestamp", None),
            }
            for t in self.trades
        ]

        # PERFORMANCE: Convert deque to list only once for metrics calculation
        equity_list = list(self._equity_history_deque)
        metrics = PerformanceMetrics.calculate_all_metrics(equity_list, trade_dicts)

        # Calculate winning/losing trades manually for count if not in metrics
        # (The metrics class does return win_rate/total_trades/profit_factor)

        # Helper to get return
        total_return = final_capital - self.initial_capital

        return BacktestResult(
            start_time=start_time,
            end_time=end_time,
            initial_capital=self.initial_capital,
            final_capital=final_capital,
            total_return=total_return,
            total_return_pct=total_return / self.initial_capital,
            total_trades=metrics.get("total_trades", 0),
            winning_trades=metrics.get("winning_trades", 0),
            losing_trades=metrics.get("losing_trades", 0),
            win_rate=metrics.get("win_rate", 0.0),
            avg_win=metrics.get("avg_win", 0.0),
            avg_loss=metrics.get("avg_loss", 0.0),
            max_drawdown=metrics.get("max_drawdown", 0.0),
            sharpe_ratio=metrics.get("sharpe_ratio", 0.0),
            trades=trade_dicts,
            equity_curve=equity_list,  # Use already-converted list
        )

    def _calculate_max_drawdown(self) -> float:
        """Calculate maximum drawdown."""
        # PERFORMANCE: Access deque directly
        if not self._equity_history_deque:
            return 0.0

        equity_values = [e["equity"] for e in self._equity_history_deque]

        peak = equity_values[0]
        max_dd = 0.0

        for equity in equity_values:
            if equity > peak:
                peak = equity

            dd = (peak - equity) / peak
            if dd > max_dd:
                max_dd = dd

        return max_dd

    def _calculate_sharpe_ratio(self) -> float:
        """Calculate Sharpe ratio (annualized)."""
        # PERFORMANCE: Access deque directly
        if len(self._equity_history_deque) < 2:
            return 0.0

        # Calculate returns
        returns = []
        equity_list = list(self._equity_history_deque)
        for i in range(1, len(equity_list)):
            prev_equity = equity_list[i - 1]["equity"]
            curr_equity = equity_list[i]["equity"]
            ret = (curr_equity - prev_equity) / prev_equity
            returns.append(ret)

        if not returns:
            return 0.0

        # Calculate Sharpe
        import numpy as np

        mean_return = np.mean(returns)
        std_return = np.std(returns)

        if std_return == 0:
            return 0.0

        # Annualize (assuming daily returns)
        sharpe = (mean_return / std_return) * np.sqrt(252)

        return sharpe
