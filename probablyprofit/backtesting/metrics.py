"""
Performance Metrics

Calculates various performance metrics for trading strategies.
"""

from typing import List, Dict, Any
import numpy as np
import pandas as pd
from loguru import logger


class PerformanceMetrics:
    """
    Calculate performance metrics for trading strategies.

    Metrics:
    - Total return, CAGR
    - Sharpe ratio, Sortino ratio
    - Maximum drawdown
    - Win rate, profit factor
    - Calmar ratio
    """

    @staticmethod
    def calculate_returns(
        equity_curve: List[Dict[str, Any]],
    ) -> pd.Series:
        """
        Calculate returns from equity curve.

        Args:
            equity_curve: List of equity snapshots

        Returns:
            Pandas Series of returns
        """
        df = pd.DataFrame(equity_curve)
        df["returns"] = df["equity"].pct_change()
        return df["returns"].dropna()

    @staticmethod
    def sharpe_ratio(
        returns: pd.Series,
        risk_free_rate: float = 0.0,
        periods_per_year: int = 252,
    ) -> float:
        """
        Calculate Sharpe ratio.

        Args:
            returns: Return series
            risk_free_rate: Annual risk-free rate
            periods_per_year: Periods per year (252 for daily)

        Returns:
            Sharpe ratio
        """
        if len(returns) == 0 or returns.std() == 0:
            return 0.0

        excess_returns = returns - (risk_free_rate / periods_per_year)
        return np.sqrt(periods_per_year) * excess_returns.mean() / returns.std()

    @staticmethod
    def sortino_ratio(
        returns: pd.Series,
        risk_free_rate: float = 0.0,
        periods_per_year: int = 252,
    ) -> float:
        """
        Calculate Sortino ratio (uses downside deviation).

        Args:
            returns: Return series
            risk_free_rate: Annual risk-free rate
            periods_per_year: Periods per year

        Returns:
            Sortino ratio
        """
        if len(returns) == 0:
            return 0.0

        excess_returns = returns - (risk_free_rate / periods_per_year)
        downside_returns = returns[returns < 0]

        if len(downside_returns) == 0 or downside_returns.std() == 0:
            return 0.0

        return np.sqrt(periods_per_year) * excess_returns.mean() / downside_returns.std()

    @staticmethod
    def max_drawdown(
        equity_curve: List[Dict[str, Any]],
    ) -> float:
        """
        Calculate maximum drawdown.

        Args:
            equity_curve: List of equity snapshots

        Returns:
            Maximum drawdown (as decimal)
        """
        if not equity_curve:
            return 0.0

        df = pd.DataFrame(equity_curve)
        equity = df["equity"]

        cumulative_max = equity.cummax()
        drawdown = (equity - cumulative_max) / cumulative_max

        return abs(drawdown.min())

    @staticmethod
    def calmar_ratio(
        returns: pd.Series,
        max_dd: float,
        periods_per_year: int = 252,
    ) -> float:
        """
        Calculate Calmar ratio (CAGR / max drawdown).

        Args:
            returns: Return series
            max_dd: Maximum drawdown
            periods_per_year: Periods per year

        Returns:
            Calmar ratio
        """
        if max_dd == 0:
            return 0.0

        cagr = (1 + returns.mean()) ** periods_per_year - 1
        return cagr / max_dd

    @staticmethod
    def calculate_all_metrics(
        equity_curve: List[Dict[str, Any]],
        trades: List[Dict[str, Any]],
    ) -> Dict[str, float]:
        """
        Calculate all performance metrics.

        Args:
            equity_curve: Equity curve data
            trades: Trade history

        Returns:
            Dictionary of all metrics
        """
        if not equity_curve:
            return {}

        # Calculate returns
        returns = PerformanceMetrics.calculate_returns(equity_curve)

        # Calculate metrics
        sharpe = PerformanceMetrics.sharpe_ratio(returns)
        sortino = PerformanceMetrics.sortino_ratio(returns)
        max_dd = PerformanceMetrics.max_drawdown(equity_curve)
        calmar = PerformanceMetrics.calmar_ratio(returns, max_dd)

        # Trade-based metrics
        total_trades = len(trades) // 2  # Assuming buy/sell pairs
        if total_trades > 0:
            # Calculate P&L for each trade pair
            pnls = []
            for i in range(0, len(trades) - 1, 2):
                buy = trades[i]
                sell = trades[i + 1] if i + 1 < len(trades) else None

                if sell:
                    pnl = buy["size"] * (sell["price"] - buy["price"])
                    pnls.append(pnl)

            wins = [p for p in pnls if p > 0]
            losses = [p for p in pnls if p < 0]

            win_rate = len(wins) / len(pnls) if pnls else 0.0
            profit_factor = (
                sum(wins) / abs(sum(losses))
                if losses and sum(losses) != 0
                else 0.0
            )
        else:
            win_rate = 0.0
            profit_factor = 0.0

        # Calculate avg win/loss
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = abs(sum(losses)) / len(losses) if losses else 0.0

        return {
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "max_drawdown": max_dd,
            "calmar_ratio": calmar,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "total_trades": total_trades,
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "avg_win": avg_win,
            "avg_loss": avg_loss,
        }
