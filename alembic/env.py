"""
Alembic Environment Configuration for ProbablyProfit

This module configures how Alembic runs migrations, including:
- Database connection setup
- Model metadata loading
- Migration script execution
"""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlmodel import SQLModel

# Import all models to ensure they're registered with SQLModel.metadata
from probablyprofit.storage.models import (
    BacktestRun,
    BalanceSnapshot,
    DecisionRecord,
    ObservationRecord,
    PerformanceMetric,
    PositionSnapshot,
    RiskStateRecord,
    TradeRecord,
)

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Model metadata for 'autogenerate' support
target_metadata = SQLModel.metadata

# Override sqlalchemy.url from environment variable if set
database_url = os.getenv("DATABASE_URL")
if database_url:
    # Convert async URL to sync URL for Alembic (it uses sync engine)
    if database_url.startswith("sqlite+aiosqlite"):
        database_url = database_url.replace("sqlite+aiosqlite", "sqlite")
    config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well. By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with the given connection."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in async mode for async database engines."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    # Check if we're using an async database URL
    url = config.get_main_option("sqlalchemy.url")
    if url and ("aiosqlite" in url or "asyncpg" in url):
        asyncio.run(run_async_migrations())
    else:
        # Standard sync migration
        from sqlalchemy import create_engine

        connectable = create_engine(
            url,
            poolclass=pool.NullPool,
        )

        with connectable.connect() as connection:
            do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
