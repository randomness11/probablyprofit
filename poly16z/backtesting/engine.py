"""
Backtest Engine

Simulates trading strategies on historical data.
"""

import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
import pandas as pd
from loguru import logger
from pydantic import BaseModel

from poly16z.api.client import Market, Order, Position
from poly16z.agent.base import BaseAgent, Observation, Decision
from poly16z.risk.manager import RiskManager


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
    """

    def __init__(
        self,
        initial_capital: float = 1000.0,
    ):
        """
        Initialize backtest engine.

        Args:
            initial_capital: Starting capital
        """
        self.initial_capital = initial_capital
        self.current_capital = initial_capital

        # Simulation state
        self.positions: Dict[str, Position] = {}
        self.trades: List[Order] = []
        self.equity_history: List[Dict[str, Any]] = []

        logger.info(f"Backtest engine initialized with ${initial_capital:,.2f}")

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
        self.equity_history = []

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

            # Record equity
            total_equity = self._calculate_total_equity(markets)
            self.equity_history.append({
                "timestamp": timestamp,
                "equity": total_equity,
                "cash": self.current_capital,
                "positions_value": total_equity - self.current_capital,
            })

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
        market = next(
            (m for m in markets if m.condition_id == decision.market_id),
            None
        )

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
                    outcome=decision.outcome or market.outcomes[0],
                    side="SELL",
                    size=position.size,
                    price=decision.price,
                    status="filled",
                )
                self.trades.append(trade)

                logger.debug(f"Executed SELL: {position.size} @ ${decision.price} (P&L: ${pnl:+.2f})")

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
            market = next(
                (m for m in markets if m.condition_id == position.market_id),
                None
            )

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
        final_capital = self.equity_history[-1]["equity"] if self.equity_history else self.initial_capital

        # Calculate trade statistics
        winning_trades = 0
        losing_trades = 0
        wins = []
        losses = []

        for i in range(0, len(self.trades), 2):
            if i + 1 >= len(self.trades):
                break

            buy_trade = self.trades[i]
            sell_trade = self.trades[i + 1]

            pnl = sell_trade.size * (sell_trade.price - buy_trade.price)

            if pnl > 0:
                winning_trades += 1
                wins.append(pnl)
            else:
                losing_trades += 1
                losses.append(abs(pnl))

        total_trades = winning_trades + losing_trades
        win_rate = winning_trades / total_trades if total_trades > 0 else 0.0
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0

        # Calculate max drawdown
        max_drawdown = self._calculate_max_drawdown()

        # Calculate Sharpe ratio
        sharpe_ratio = self._calculate_sharpe_ratio()

        return BacktestResult(
            start_time=start_time,
            end_time=end_time,
            initial_capital=self.initial_capital,
            final_capital=final_capital,
            total_return=final_capital - self.initial_capital,
            total_return_pct=(final_capital - self.initial_capital) / self.initial_capital,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            trades=[
                {
                    "market_id": t.market_id,
                    "side": t.side,
                    "size": t.size,
                    "price": t.price,
                }
                for t in self.trades
            ],
            equity_curve=self.equity_history,
        )

    def _calculate_max_drawdown(self) -> float:
        """Calculate maximum drawdown."""
        if not self.equity_history:
            return 0.0

        equity_values = [e["equity"] for e in self.equity_history]

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
        if len(self.equity_history) < 2:
            return 0.0

        # Calculate returns
        returns = []
        for i in range(1, len(self.equity_history)):
            prev_equity = self.equity_history[i-1]["equity"]
            curr_equity = self.equity_history[i]["equity"]
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
