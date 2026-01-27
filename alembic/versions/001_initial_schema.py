"""Initial schema - create all tables

Revision ID: 001_initial
Revises:
Create Date: 2025-01-15

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create trades table
    op.create_table(
        "trades",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.String(), nullable=True),
        sa.Column("market_id", sa.String(), nullable=False),
        sa.Column("market_question", sa.String(), nullable=True),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("side", sa.String(), nullable=False),
        sa.Column("size", sa.Float(), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("filled_size", sa.Float(), nullable=False, default=0.0),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("observation_id", sa.Integer(), nullable=True),
        sa.Column("decision_id", sa.Integer(), nullable=True),
        sa.Column("realized_pnl", sa.Float(), nullable=True),
        sa.Column("fees", sa.Float(), nullable=False, default=0.0),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_trades_order_id"), "trades", ["order_id"], unique=False)
    op.create_index(op.f("ix_trades_market_id"), "trades", ["market_id"], unique=False)
    op.create_index(op.f("ix_trades_timestamp"), "trades", ["timestamp"], unique=False)

    # Create observations table
    op.create_table(
        "observations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("balance", sa.Float(), nullable=False),
        sa.Column("num_markets", sa.Integer(), nullable=False),
        sa.Column("num_positions", sa.Integer(), nullable=False),
        sa.Column("markets_json", sa.String(), nullable=False),
        sa.Column("positions_json", sa.String(), nullable=False, default="{}"),
        sa.Column("signals_json", sa.String(), nullable=False, default="{}"),
        sa.Column("metadata_json", sa.String(), nullable=False, default="{}"),
        sa.Column("news_context", sa.String(), nullable=True),
        sa.Column("sentiment_summary", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_observations_timestamp"), "observations", ["timestamp"], unique=False)

    # Create decisions table
    op.create_table(
        "decisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("market_id", sa.String(), nullable=True),
        sa.Column("outcome", sa.String(), nullable=True),
        sa.Column("size", sa.Float(), nullable=False, default=0.0),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("reasoning", sa.String(), nullable=False, default=""),
        sa.Column("confidence", sa.Float(), nullable=False, default=0.5),
        sa.Column("metadata_json", sa.String(), nullable=False, default="{}"),
        sa.Column("observation_id", sa.Integer(), nullable=True),
        sa.Column("agent_name", sa.String(), nullable=False, default="unknown"),
        sa.Column("agent_type", sa.String(), nullable=False, default="unknown"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_decisions_timestamp"), "decisions", ["timestamp"], unique=False)
    op.create_index(op.f("ix_decisions_market_id"), "decisions", ["market_id"], unique=False)

    # Create position_snapshots table
    op.create_table(
        "position_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("market_id", sa.String(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("size", sa.Float(), nullable=False),
        sa.Column("avg_price", sa.Float(), nullable=False),
        sa.Column("current_price", sa.Float(), nullable=False),
        sa.Column("unrealized_pnl", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_position_snapshots_timestamp"), "position_snapshots", ["timestamp"], unique=False
    )
    op.create_index(
        op.f("ix_position_snapshots_market_id"), "position_snapshots", ["market_id"], unique=False
    )

    # Create balance_snapshots table
    op.create_table(
        "balance_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("balance", sa.Float(), nullable=False),
        sa.Column("total_exposure", sa.Float(), nullable=False),
        sa.Column("num_positions", sa.Integer(), nullable=False),
        sa.Column("daily_pnl", sa.Float(), nullable=False),
        sa.Column("total_pnl", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_balance_snapshots_timestamp"), "balance_snapshots", ["timestamp"], unique=False
    )

    # Create performance_metrics table
    op.create_table(
        "performance_metrics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("date", sa.DateTime(), nullable=False),
        sa.Column("daily_return", sa.Float(), nullable=False),
        sa.Column("cumulative_return", sa.Float(), nullable=False),
        sa.Column("sharpe_ratio", sa.Float(), nullable=False),
        sa.Column("max_drawdown", sa.Float(), nullable=False),
        sa.Column("volatility", sa.Float(), nullable=False),
        sa.Column("total_trades", sa.Integer(), nullable=False),
        sa.Column("win_rate", sa.Float(), nullable=False),
        sa.Column("avg_win", sa.Float(), nullable=False),
        sa.Column("avg_loss", sa.Float(), nullable=False),
        sa.Column("profit_factor", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_performance_metrics_date"), "performance_metrics", ["date"], unique=False
    )

    # Create backtest_runs table
    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("strategy", sa.String(), nullable=False),
        sa.Column("agent_type", sa.String(), nullable=False),
        sa.Column("start_date", sa.DateTime(), nullable=False),
        sa.Column("end_date", sa.DateTime(), nullable=False),
        sa.Column("initial_capital", sa.Float(), nullable=False),
        sa.Column("final_capital", sa.Float(), nullable=False),
        sa.Column("total_return_pct", sa.Float(), nullable=False),
        sa.Column("sharpe_ratio", sa.Float(), nullable=False),
        sa.Column("max_drawdown", sa.Float(), nullable=False),
        sa.Column("total_trades", sa.Integer(), nullable=False),
        sa.Column("win_rate", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("config_json", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create risk_state table
    op.create_table(
        "risk_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("initial_capital", sa.Float(), nullable=False),
        sa.Column("current_capital", sa.Float(), nullable=False),
        sa.Column("current_exposure", sa.Float(), nullable=False),
        sa.Column("daily_pnl", sa.Float(), nullable=False),
        sa.Column("open_positions_json", sa.String(), nullable=False, default="{}"),
        sa.Column("trades_json", sa.String(), nullable=False, default="[]"),
        sa.Column("agent_name", sa.String(), nullable=False, default="unknown"),
        sa.Column("is_latest", sa.Boolean(), nullable=False, default=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_risk_state_timestamp"), "risk_state", ["timestamp"], unique=False)


def downgrade() -> None:
    op.drop_table("risk_state")
    op.drop_table("backtest_runs")
    op.drop_table("performance_metrics")
    op.drop_table("balance_snapshots")
    op.drop_table("position_snapshots")
    op.drop_table("decisions")
    op.drop_table("observations")
    op.drop_table("trades")
