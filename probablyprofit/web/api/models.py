"""
API Response Models

Pydantic models for REST API requests and responses.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """
    Standard error response for API errors.

    Frontend can check for this format to display user-friendly error messages.
    """

    error: str  # User-friendly error message
    code: str  # Error code for programmatic handling (e.g., "AGENT_NOT_INITIALIZED")
    details: Optional[str] = None  # Technical details for debugging (optional)


class HealthResponse(BaseModel):
    """Health check response for monitoring systems."""

    status: str  # "healthy", "degraded", "unhealthy"
    timestamp: datetime
    version: str
    uptime_seconds: float
    checks: dict  # Individual component health checks


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


class PositionExposure(BaseModel):
    """Single position exposure details."""

    market_id: str
    market_question: str
    outcome: str
    size: float
    entry_price: float
    current_price: float
    value: float
    pnl: float
    pnl_pct: float
    correlation_group: Optional[str] = None
    has_trailing_stop: bool = False
    stop_price: Optional[float] = None


class CorrelationGroup(BaseModel):
    """Correlated positions group."""

    group_name: str
    total_exposure: float
    positions_count: int
    markets: List[str]
    risk_level: str  # low, medium, high


class ExposureResponse(BaseModel):
    """Full portfolio exposure response."""

    total_value: float
    total_exposure: float
    cash_balance: float
    positions: List[PositionExposure]
    correlation_groups: List[CorrelationGroup]
    exposure_by_category: dict  # category -> exposure amount
    risk_metrics: dict  # various risk metrics
    warnings: List[str]  # active risk warnings


class PaperPositionResponse(BaseModel):
    """Paper trading position response."""

    market_id: str
    market_question: str
    side: str
    size: float
    avg_price: float
    current_price: float
    value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float


class PaperTradeResponse(BaseModel):
    """Paper trade response."""

    trade_id: str
    timestamp: datetime
    market_id: str
    side: str
    action: str
    size: float
    price: float
    value: float
    fees: float


class PaperPortfolioResponse(BaseModel):
    """Paper trading portfolio response."""

    enabled: bool
    initial_capital: float
    cash: float
    positions_value: float
    total_value: float
    total_return: float
    total_return_pct: float
    realized_pnl: float
    unrealized_pnl: float
    total_fees: float
    positions_count: int
    trades_count: int
    positions: List[PaperPositionResponse]
    recent_trades: List[PaperTradeResponse]
