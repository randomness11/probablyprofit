"""
Database Manager

Handles database connections and session management with async support.
"""

from sqlmodel import create_engine, Session, SQLModel
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
from loguru import logger
import os


class DatabaseManager:
    """Manages database connections and sessions."""

    def __init__(self, database_url: str = "sqlite+aiosqlite:///probablyprofit.db"):
        self.database_url = database_url
        self.engine = create_async_engine(
            database_url,
            echo=False,
            connect_args={"check_same_thread": False}
            if "sqlite" in database_url
            else {},
        )
        self.async_session_maker = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        logger.info(f"DatabaseManager initialized with URL: {database_url}")

    async def create_tables(self):
        """Create all tables."""
        async with self.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        logger.info("Database tables created")

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
