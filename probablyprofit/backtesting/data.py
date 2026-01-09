"""
Backtest Data Generator

Generates synthetic market data for backtesting.
"""

from typing import List, Dict, Any
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from probablyprofit.api.client import Market

class MockDataGenerator:
    """
    Generates synthetic market data for backtesting.
    
    Uses Geometric Brownian Motion (GBM) to simulate realistic price paths.
    """
    
    def __init__(self, seed: int = 42):
        self.rng = np.random.default_rng(seed)
        
    def generate_price_path(
        self,
        start_price: float = 0.5,
        days: int = 30,
        interval_minutes: int = 60,
        volatility: float = 0.5,  # Annualized vol
        drift: float = 0.0,
    ) -> pd.Series:
        """
        Generate a single price path using GBM.
        
        Args:
            start_price: Starting price
            days: Duration in days
            interval_minutes: Data interval
            volatility: Annualized volatility
            drift: Annualized drift
            
        Returns:
            Pandas Series with datetime index and prices
        """
        # Calculate steps
        steps_per_day = 24 * 60 // interval_minutes
        total_steps = days * steps_per_day
        dt = 1 / (365 * steps_per_day)  # Time step in years
        
        # Generate random returns
        # GBM: dS = S * (mu*dt + sigma*dW)
        # S(t) = S(0) * exp((mu - 0.5*sigma^2)*t + sigma*W(t))
        
        t = np.linspace(0, days/365, total_steps)
        W = self.rng.standard_normal(total_steps).cumsum() * np.sqrt(dt)
        
        drift_term = (drift - 0.5 * volatility**2)
        exponent = drift_term * t + volatility * W
        
        prices = start_price * np.exp(exponent)
        
        # Clamp prices between 0.01 and 0.99 for binary markets
        prices = np.clip(prices, 0.01, 0.99)
        
        # Create timestamps
        start_time = datetime.now() - timedelta(days=days)
        timestamps = [
            start_time + timedelta(minutes=i*interval_minutes) 
            for i in range(total_steps)
        ]
        
        return pd.Series(prices, index=timestamps)

    def generate_market_scenario(
        self,
        num_markets: int = 5,
        days: int = 30,
    ) -> List[List[Market]]:
        """
        Generate a full market scenario.
        
        Args:
            num_markets: Number of markets to simulate
            days: Duration in days
            
        Returns:
            List of (List[Market]) snapshots, one per timestep
        """
        scenarios = []
        timestamps = []
        
        # Generate paths for each market
        market_paths = []
        for i in range(num_markets):
            # Random parameters for variety
            start_price = self.rng.uniform(0.1, 0.9)
            vol = self.rng.uniform(0.2, 0.8)
            drift = self.rng.normal(0, 0.1)
            
            path = self.generate_price_path(
                start_price=start_price,
                days=days,
                volatility=vol,
                drift=drift
            )
            market_paths.append((f"market_{i}", path))
            
            if i == 0:
                timestamps = path.index.tolist()
                
        # Construct snapshots
        snapshots = []
        for t_idx, timestamp in enumerate(timestamps):
            markets_at_t = []
            for m_id, path in market_paths:
                price = path.iloc[t_idx]
                
                market = Market(
                    condition_id=m_id,
                    question=f"Market {m_id} Prediction?",
                    outcomes=["YES", "NO"],
                    outcome_prices=[price, 1-price],
                    volume=10000.0,
                    liquidity=5000.0,
                    end_date=timestamp + timedelta(days=5),
                )
                markets_at_t.append(market)
            
            snapshots.append(markets_at_t)
            
        return snapshots, timestamps
