#!/usr/bin/env python3
"""
Strategy Optimizer CLI

Optimize strategy parameters using grid search and Monte Carlo simulation.

Usage:
    python scripts/optimize.py --days 30 --simulations 50
"""

import asyncio
import argparse
import sys
import os

# Add project root to path (probablyprofit package is at <root>/probablyprofit)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from loguru import logger
from probablyprofit.api.client import PolymarketClient
from probablyprofit.risk.manager import RiskManager
from probablyprofit.agent.mock_agent import create_mock_agent_factory
from probablyprofit.backtesting.optimizer import (
    StrategyOptimizer,
    ParameterRange,
    print_optimization_report,
)


def parse_args():
    parser = argparse.ArgumentParser(description="Optimize strategy parameters")
    parser.add_argument("--days", type=int, default=30,
                        help="Days of synthetic data for testing")
    parser.add_argument("--simulations", type=int, default=50,
                        help="Number of Monte Carlo simulations")
    parser.add_argument("--metric", type=str, default="sharpe_ratio",
                        choices=["sharpe_ratio", "total_return_pct", "win_rate"],
                        help="Metric to optimize")
    return parser.parse_args()


async def main():
    args = parse_args()
    
    logger.info("🔧 Starting Strategy Optimizer")
    
    # Initialize
    client = PolymarketClient()
    risk = RiskManager(initial_capital=1000.0)
    
    # Create agent factory
    factory = create_mock_agent_factory(client, risk)
    
    # Initialize optimizer
    optimizer = StrategyOptimizer(
        agent_factory=factory,
        initial_capital=1000.0,
        data_days=args.days,
    )
    
    # Define parameter ranges
    param_ranges = [
        ParameterRange("buy_threshold", [0.3, 0.35, 0.4, 0.45]),
        ParameterRange("sell_threshold", [0.55, 0.6, 0.65, 0.7]),
        ParameterRange("confidence", [0.6, 0.7, 0.8]),
    ]
    
    # Run grid search
    logger.info("📊 Running Grid Search...")
    result = await optimizer.grid_search(param_ranges, metric=args.metric)
    
    # Print results
    print_optimization_report(result)
    
    # Run Monte Carlo on best params
    logger.info("🎲 Running Monte Carlo Simulation...")
    mc_results = await optimizer.monte_carlo(
        result.best_params,
        num_simulations=args.simulations
    )
    
    print("\n" + "="*60)
    print("🎲 MONTE CARLO ROBUSTNESS TEST")
    print("="*60)
    print(f"Simulations: {mc_results['num_simulations']}")
    print(f"Return: {mc_results['return_mean']:+.2%} ± {mc_results['return_std']:.2%}")
    print(f"5th Percentile: {mc_results['return_5th_percentile']:+.2%}")
    print(f"95th Percentile: {mc_results['return_95th_percentile']:+.2%}")
    print(f"Sharpe: {mc_results['sharpe_mean']:.2f} ± {mc_results['sharpe_std']:.2f}")
    print(f"Worst Drawdown: {mc_results['max_drawdown_worst']:.2%}")
    print("="*60 + "\n")
    
    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
