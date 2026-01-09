"""
API Response Models

Pydantic models for REST API requests and responses.
"""

from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class StatusResponse(BaseModel):
    """Agent status response."""

    running: bool
    agent_name: str
    agent_type: str
    strategy: str
    dry_run: bool
    uptime_seconds: float
    loop_count: int
    last_observation: Optional[datetime] = None
    balance: float
    positions_count: int


class TradeResponse(BaseModel):
    """Trade record response."""

    id: int
    order_id: Optional[str]
    market_id: str
    outcome: str
    side: str
    size: float
    price: float
    status: str
    timestamp: datetime
    realized_pnl: Optional[float]


class PerformanceResponse(BaseModel):
    """Performance metrics response."""

    current_capital: float
    initial_capital: float
    total_return: float
    total_return_pct: float
    total_pnl: float
    daily_pnl: float
    win_rate: float
    total_trades: int


class EquityCurvePoint(BaseModel):
    """Equity curve data point."""

    timestamp: datetime
    equity: float
    cash: float
    positions_value: float


class MarketResponse(BaseModel):
    """Market information response."""

    condition_id: str
    question: str
    description: Optional[str]
    end_date: datetime
    outcomes: List[str]
    outcome_prices: List[float]
    volume: float
    liquidity: float
    active: bool
