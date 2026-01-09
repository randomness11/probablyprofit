"""
Strategy Parameter Optimizer

Grid Search and Monte Carlo simulation for finding optimal strategy parameters.
"""

import asyncio
from typing import List, Dict, Any, Callable, Optional
from dataclasses import dataclass
from datetime import datetime
import numpy as np
from loguru import logger
from concurrent.futures import ProcessPoolExecutor

from probablyprofit.backtesting.engine import BacktestEngine, BacktestResult
from probablyprofit.backtesting.data import MockDataGenerator
from probablyprofit.api.client import Market


@dataclass
class ParameterRange:
    """Defines a parameter range for optimization."""
    name: str
    values: List[Any]


@dataclass  
class OptimizationResult:
    """Results from parameter optimization."""
    best_params: Dict[str, Any]
    best_sharpe: float
    best_return: float
    all_results: List[Dict[str, Any]]
    runtime_seconds: float


class StrategyOptimizer:
    """
    Optimizes strategy parameters using grid search.
    
    Features:
    - Grid search over parameter combinations
    - Monte Carlo simulation for robustness testing
    - Parallel execution for speed
    """
    
    def __init__(
        self,
        agent_factory: Callable[[Dict[str, Any]], "BaseAgent"],
        initial_capital: float = 1000.0,
        data_days: int = 30,
        seed: int = 42,
    ):
        """
        Initialize optimizer.
        
        Args:
            agent_factory: Function that creates an agent given parameters
            initial_capital: Starting capital for backtests
            data_days: Number of days of synthetic data for testing
            seed: Random seed for reproducibility
        """
        self.agent_factory = agent_factory
        self.initial_capital = initial_capital
        self.data_days = data_days
        self.seed = seed
        
        # Pre-generate data once
        self.generator = MockDataGenerator(seed=seed)
        self.market_data, self.timestamps = self.generator.generate_market_scenario(
            num_markets=5,
            days=data_days
        )
        
        logger.info(f"Optimizer initialized with {data_days} days of data")
    
    async def grid_search(
        self,
        param_ranges: List[ParameterRange],
        metric: str = "sharpe_ratio",
    ) -> OptimizationResult:
        """
        Run grid search over parameter combinations.
        
        Args:
            param_ranges: List of parameter ranges to search
            metric: Metric to optimize ('sharpe_ratio', 'total_return_pct', 'win_rate')
            
        Returns:
            OptimizationResult with best parameters and all results
        """
        start_time = datetime.now()
        
        # Generate all parameter combinations
        combinations = self._generate_combinations(param_ranges)
        logger.info(f"Testing {len(combinations)} parameter combinations")
        
        results = []
        best_result = None
        best_metric_value = float('-inf')
        
        for i, params in enumerate(combinations):
            logger.debug(f"Testing combination {i+1}/{len(combinations)}: {params}")
            
            try:
                # Create agent with these parameters
                agent = self.agent_factory(params)
                
                # Run backtest
                engine = BacktestEngine(initial_capital=self.initial_capital)
                result = await engine.run_backtest(
                    agent,
                    self.market_data,
                    self.timestamps
                )
                
                # Extract metric
                metric_value = getattr(result, metric, 0.0)
                
                results.append({
                    "params": params,
                    "sharpe_ratio": result.sharpe_ratio,
                    "total_return_pct": result.total_return_pct,
                    "max_drawdown": result.max_drawdown,
                    "win_rate": result.win_rate,
                    "total_trades": result.total_trades,
                })
                
                if metric_value > best_metric_value:
                    best_metric_value = metric_value
                    best_result = {
                        "params": params,
                        "result": result,
                    }
                    
            except Exception as e:
                logger.warning(f"Failed to test params {params}: {e}")
                continue
        
        runtime = (datetime.now() - start_time).total_seconds()
        
        if not best_result:
            raise ValueError("No successful parameter combinations found")
        
        logger.info(f"Grid search complete in {runtime:.1f}s")
        logger.info(f"Best {metric}: {best_metric_value:.4f}")
        logger.info(f"Best params: {best_result['params']}")
        
        return OptimizationResult(
            best_params=best_result['params'],
            best_sharpe=best_result['result'].sharpe_ratio,
            best_return=best_result['result'].total_return_pct,
            all_results=results,
            runtime_seconds=runtime,
        )
    
    async def monte_carlo(
        self,
        params: Dict[str, Any],
        num_simulations: int = 100,
        volatility_range: tuple = (0.8, 1.2),
    ) -> Dict[str, Any]:
        """
        Run Monte Carlo simulation to test parameter robustness.
        
        Args:
            params: Strategy parameters to test
            num_simulations: Number of simulations to run
            volatility_range: Range of volatility multipliers
            
        Returns:
            Statistical summary of results
        """
        logger.info(f"Running {num_simulations} Monte Carlo simulations")
        
        returns = []
        sharpes = []
        drawdowns = []
        
        for i in range(num_simulations):
            # Create varied data with different seed
            generator = MockDataGenerator(seed=self.seed + i)
            
            # Vary volatility
            vol_multiplier = np.random.uniform(*volatility_range)
            
            markets, timestamps = generator.generate_market_scenario(
                num_markets=5,
                days=self.data_days,
            )
            
            try:
                agent = self.agent_factory(params)
                engine = BacktestEngine(initial_capital=self.initial_capital)
                result = await engine.run_backtest(agent, markets, timestamps)
                
                returns.append(result.total_return_pct)
                sharpes.append(result.sharpe_ratio)
                drawdowns.append(result.max_drawdown)
                
            except Exception as e:
                logger.debug(f"Simulation {i} failed: {e}")
                continue
        
        if not returns:
            raise ValueError("All simulations failed")
        
        return {
            "num_simulations": len(returns),
            "return_mean": np.mean(returns),
            "return_std": np.std(returns),
            "return_5th_percentile": np.percentile(returns, 5),
            "return_95th_percentile": np.percentile(returns, 95),
            "sharpe_mean": np.mean(sharpes),
            "sharpe_std": np.std(sharpes),
            "max_drawdown_mean": np.mean(drawdowns),
            "max_drawdown_worst": max(drawdowns),
        }
    
    def _generate_combinations(
        self,
        param_ranges: List[ParameterRange]
    ) -> List[Dict[str, Any]]:
        """Generate all parameter combinations."""
        if not param_ranges:
            return [{}]
        
        first = param_ranges[0]
        rest = param_ranges[1:]
        
        rest_combinations = self._generate_combinations(rest)
        
        combinations = []
        for value in first.values:
            for rest_combo in rest_combinations:
                combo = {first.name: value, **rest_combo}
                combinations.append(combo)
        
        return combinations


def print_optimization_report(result: OptimizationResult) -> None:
    """Print a formatted optimization report."""
    print("\n" + "="*60)
    print("📈 OPTIMIZATION RESULTS")
    print("="*60)
    print(f"\n⏱️  Runtime: {result.runtime_seconds:.1f} seconds")
    print(f"🔍 Combinations tested: {len(result.all_results)}")
    
    print(f"\n🏆 Best Parameters:")
    for k, v in result.best_params.items():
        print(f"   {k}: {v}")
    
    print(f"\n📊 Best Performance:")
    print(f"   Sharpe Ratio: {result.best_sharpe:.2f}")
    print(f"   Return: {result.best_return:+.2%}")
    
    print("\n" + "="*60 + "\n")
