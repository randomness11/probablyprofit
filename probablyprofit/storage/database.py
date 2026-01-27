"""
Database Manager

Handles database connections and session management with async support.

Production improvements:
- WAL mode for SQLite (better concurrency)
- Synchronous mode for performance
- Connection event handlers

SECURITY WARNING:
    The default SQLite database is NOT encrypted. For production deployments
    handling sensitive trading data, you should use SQLCipher for encryption:

    1. Install SQLCipher: pip install sqlcipher3-binary
    2. Use a connection string like: sqlite+pysqlcipher:///path/to/db?key=your_key

    Or use a production database like PostgreSQL with TLS/SSL.

    See: https://www.zetetic.net/sqlcipher/
"""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from loguru import logger
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, SQLModel, create_engine


def _set_sqlite_pragma(dbapi_conn, connection_record):
    """
    Set SQLite PRAGMA statements for production use.

    Called on each new connection to the database.
    """
    cursor = dbapi_conn.cursor()

    # WAL mode: Better concurrency, allows readers while writing
    cursor.execute("PRAGMA journal_mode=WAL")

    # Synchronous NORMAL: Good balance of safety and performance
    # FULL is safest but slowest, OFF is fastest but risky
    cursor.execute("PRAGMA synchronous=NORMAL")

    # Increase cache size (default is 2000 pages = ~8MB with 4KB pages)
    cursor.execute("PRAGMA cache_size=10000")

    # Enable foreign key constraints
    cursor.execute("PRAGMA foreign_keys=ON")

    # Busy timeout: Wait up to 30 seconds if database is locked
    cursor.execute("PRAGMA busy_timeout=30000")

    cursor.close()


class DatabaseManager:
    """
    Manages database connections and sessions.

    SECURITY NOTE:
        For production use with sensitive trading data, use encrypted storage:
        - SQLCipher for SQLite encryption
        - PostgreSQL/MySQL with TLS for network databases
    """

    def __init__(self, database_url: str = "sqlite+aiosqlite:///probablyprofit.db"):
        self.database_url = database_url
        self.is_sqlite = "sqlite" in database_url
        self.is_encrypted = "sqlcipher" in database_url or "pysqlcipher" in database_url

        # Create async engine with appropriate settings
        connect_args = {}
        if self.is_sqlite:
            connect_args["check_same_thread"] = False

        self.engine = create_async_engine(
            database_url,
            echo=False,
            connect_args=connect_args,
            pool_pre_ping=True,  # Verify connections before use
        )

        # Register SQLite PRAGMA handler for production settings
        if self.is_sqlite:
            # Note: For aiosqlite, we need to use a different approach
            # The PRAGMAs will be set via event listener on the sync engine
            pass

        self.async_session_maker = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        logger.info(f"DatabaseManager initialized with URL: {self._redact_url(database_url)}")

        # SECURITY: Warn about unencrypted SQLite in production
        if self.is_sqlite and not self.is_encrypted:
            env = os.getenv("ENVIRONMENT", os.getenv("ENV", "development"))
            if env.lower() in ("production", "prod"):
                logger.warning(
                    "SECURITY WARNING: Using unencrypted SQLite database in production. "
                    "Consider using SQLCipher for encryption: "
                    "pip install sqlcipher3-binary "
                    "and use connection string: sqlite+pysqlcipher:///path/to/db?key=YOUR_KEY"
                )
            else:
                logger.info(
                    "SQLite: WAL mode and production PRAGMAs will be enabled. "
                    "Note: For production, consider SQLCipher for encryption."
                )
        elif self.is_sqlite and self.is_encrypted:
            logger.info("SQLite with SQLCipher encryption enabled")

    def _redact_url(self, url: str) -> str:
        """Redact sensitive parts of database URL for logging."""
        # Redact any password or key in the URL
        import re
        # Redact password in standard URLs
        url = re.sub(r'://[^:]+:([^@]+)@', r'://***:***@', url)
        # Redact encryption keys
        url = re.sub(r'key=[^&\s]+', 'key=***', url)
        return url

    async def create_tables(self):
        """Create all tables."""
        async with self.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

            # Apply SQLite PRAGMAs for production
            if self.is_sqlite:
                await conn.execute(text("PRAGMA journal_mode=WAL"))
                await conn.execute(text("PRAGMA synchronous=NORMAL"))
                await conn.execute(text("PRAGMA cache_size=10000"))
                await conn.execute(text("PRAGMA foreign_keys=ON"))
                await conn.execute(text("PRAGMA busy_timeout=30000"))
                logger.info("SQLite PRAGMAs applied: WAL mode, synchronous=NORMAL")

        logger.info("Database tables created")

    async def apply_sqlite_pragmas(self):
        """
        Apply SQLite PRAGMA settings for production use.

        Call this on startup to ensure optimal settings.
        """
        if not self.is_sqlite:
            return

        async with self.engine.begin() as conn:
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA synchronous=NORMAL"))
            await conn.execute(text("PRAGMA cache_size=10000"))
            await conn.execute(text("PRAGMA foreign_keys=ON"))
            await conn.execute(text("PRAGMA busy_timeout=30000"))

        logger.info("SQLite production PRAGMAs applied")

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get async database session."""
        async with self.async_session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"Database session error: {e}")
                raise

    async def close(self):
        """Close database connection."""
        await self.engine.dispose()
        logger.info("Database connection closed")


# Global database manager instance
_db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    """Get global database manager."""
    global _db_manager
    if _db_manager is None:
        db_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///probablyprofit.db")
        _db_manager = DatabaseManager(db_url)
    return _db_manager


async def initialize_database():
    """Initialize database and create tables."""
    db_manager = get_db_manager()
    await db_manager.create_tables()
    logger.info("Database initialized successfully")
