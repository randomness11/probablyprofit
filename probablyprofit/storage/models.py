"""
Database Models

SQLModel ORM models for persistent storage of trading data.
"""

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class TradeRecord(SQLModel, table=True):
    """Persistent record of executed trades."""

    __tablename__ = "trades"

    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: Optional[str] = Field(default=None, index=True)
    market_id: str = Field(index=True)
    market_question: Optional[str] = Field(default=None, index=True)  # Searchable market name
    outcome: str
    side: str  # BUY/SELL
    size: float
    price: float
    status: str
    filled_size: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.now, index=True)

    # Relationships
    observation_id: Optional[int] = Field(default=None)
    decision_id: Optional[int] = Field(default=None)

    # P&L tracking
    realized_pnl: Optional[float] = None
    fees: float = 0.0


class ObservationRecord(SQLModel, table=True):
    """Historical market observations."""

    __tablename__ = "observations"

    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.now, index=True)
    balance: float
    num_markets: int
    num_positions: int

    # JSON fields for complex data
    markets_json: str  # JSON serialized list of markets
    positions_json: str = "{}"
    signals_json: str = "{}"
    metadata_json: str = "{}"

    # Intelligence layer data
    news_context: Optional[str] = None
    sentiment_summary: Optional[str] = None


class DecisionRecord(SQLModel, table=True):
    """AI agent decisions."""

    __tablename__ = "decisions"

    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.now, index=True)
    action: str  # buy, sell, hold, close
    market_id: Optional[str] = Field(default=None, index=True)
    outcome: Optional[str] = None
    size: float = 0.0
    price: Optional[float] = None
    reasoning: str = ""
    confidence: float = 0.5
    metadata_json: str = "{}"

    # Link to observation
    observation_id: Optional[int] = Field(default=None)

    # Agent info
    agent_name: str = "unknown"
    agent_type: str = "unknown"  # openai, gemini, anthropic, ensemble


class PositionSnapshot(SQLModel, table=True):
    """Snapshots of positions over time."""

    __tablename__ = "position_snapshots"

    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.now, index=True)
    market_id: str = Field(index=True)
    outcome: str
    size: float
    avg_price: float
    current_price: float
    unrealized_pnl: float


class BalanceSnapshot(SQLModel, table=True):
    """Daily balance snapshots for performance tracking."""

    __tablename__ = "balance_snapshots"

    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.now, index=True)
    balance: float
    total_exposure: float
    num_positions: int
    daily_pnl: float
    total_pnl: float


class PerformanceMetric(SQLModel, table=True):
    """Aggregated performance metrics."""

    __tablename__ = "performance_metrics"

    id: Optional[int] = Field(default=None, primary_key=True)
    date: datetime = Field(default_factory=datetime.now, index=True)

    # Returns
    daily_return: float
    cumulative_return: float

    # Risk metrics
    sharpe_ratio: float
    max_drawdown: float
    volatility: float

    # Trading metrics
    total_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float


class BacktestRun(SQLModel, table=True):
    """Historical backtest runs."""

    __tablename__ = "backtest_runs"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    strategy: str
    agent_type: str
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_capital: float
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown: float
    total_trades: int
    win_rate: float
    created_at: datetime = Field(default_factory=datetime.now)
    config_json: str  # Full config snapshot


class RiskStateRecord(SQLModel, table=True):
    """Persisted risk manager state for crash recovery."""

    __tablename__ = "risk_state"

    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.now, index=True)

    # Core state
    initial_capital: float
    current_capital: float
    current_exposure: float
    daily_pnl: float

    # Positions as JSON: {"market_id": size, ...}
    open_positions_json: str = "{}"

    # Trade history as JSON array
    trades_json: str = "[]"

    # Metadata
    agent_name: str = "unknown"
    is_latest: bool = True  # Only one record should be "latest"
