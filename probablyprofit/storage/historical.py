"""
Historical Data Storage

Stores real market data for backtesting and analysis.
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from loguru import logger

try:
    import aiosqlite
    AIOSQLITE_AVAILABLE = True
except ImportError:
    AIOSQLITE_AVAILABLE = False


@dataclass
class MarketSnapshot:
    """A snapshot of a market at a point in time."""
    condition_id: str
    question: str
    timestamp: datetime
    yes_price: float
    no_price: float
    volume: float
    liquidity: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PricePoint:
    """A single price point in time series."""
    condition_id: str
    timestamp: datetime
    yes_price: float
    no_price: float
    volume: float = 0.0


class HistoricalDataStore:
    """
    SQLite-based storage for historical market data.

    Features:
    - Automatic schema creation
    - Efficient time-range queries
    - Data aggregation (OHLC)
    - Data export to pandas/CSV

    Usage:
        store = HistoricalDataStore()
        await store.initialize()

        # Record snapshots
        await store.record_snapshot(market)

        # Query history
        history = await store.get_price_history("0x123", days=30)
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        retention_days: int = 365,
    ):
        """
        Initialize historical data store.

        Args:
            db_path: Path to SQLite database
            retention_days: Days to retain data
        """
        if not AIOSQLITE_AVAILABLE:
            raise ImportError("aiosqlite required. Install with: pip install aiosqlite")

        if db_path is None:
            data_dir = Path.home() / ".probablyprofit" / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(data_dir / "historical.db")

        self.db_path = db_path
        self.retention_days = retention_days
        self._initialized = False

        logger.info(f"HistoricalDataStore initialized (path: {db_path})")

    async def initialize(self) -> None:
        """Initialize database schema."""
        async with aiosqlite.connect(self.db_path) as db:
            # Market snapshots table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS market_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    condition_id TEXT NOT NULL,
                    question TEXT,
                    timestamp DATETIME NOT NULL,
                    yes_price REAL NOT NULL,
                    no_price REAL NOT NULL,
                    volume REAL DEFAULT 0,
                    liquidity REAL DEFAULT 0,
                    metadata TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Index for efficient queries
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_snapshots_market_time
                ON market_snapshots (condition_id, timestamp)
            """)

            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_snapshots_timestamp
                ON market_snapshots (timestamp)
            """)

            # Price points table (more granular)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS price_points (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    condition_id TEXT NOT NULL,
                    timestamp DATETIME NOT NULL,
                    yes_price REAL NOT NULL,
                    no_price REAL NOT NULL,
                    volume REAL DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_prices_market_time
                ON price_points (condition_id, timestamp)
            """)

            # Trade history table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS trade_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    market_id TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    side TEXT NOT NULL,
                    size REAL NOT NULL,
                    price REAL NOT NULL,
                    pnl REAL DEFAULT 0,
                    timestamp DATETIME NOT NULL,
                    agent_name TEXT,
                    strategy TEXT,
                    metadata TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_trades_timestamp
                ON trade_history (timestamp)
            """)

            await db.commit()

        self._initialized = True
        logger.info("[HistoricalDataStore] Database initialized")

    async def record_snapshot(
        self,
        condition_id: str,
        question: str,
        yes_price: float,
        no_price: float,
        volume: float = 0.0,
        liquidity: float = 0.0,
        metadata: Optional[Dict] = None,
    ) -> None:
        """
        Record a market snapshot.

        Args:
            condition_id: Market condition ID
            question: Market question
            yes_price: Current YES price
            no_price: Current NO price
            volume: Trading volume
            liquidity: Market liquidity
            metadata: Additional metadata
        """
        if not self._initialized:
            await self.initialize()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO market_snapshots
                (condition_id, question, timestamp, yes_price, no_price, volume, liquidity, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    condition_id,
                    question,
                    datetime.now().isoformat(),
                    yes_price,
                    no_price,
                    volume,
                    liquidity,
                    json.dumps(metadata) if metadata else None,
                )
            )
            await db.commit()

    async def record_price(
        self,
        condition_id: str,
        yes_price: float,
        no_price: float,
        volume: float = 0.0,
    ) -> None:
        """Record a price point."""
        if not self._initialized:
            await self.initialize()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO price_points
                (condition_id, timestamp, yes_price, no_price, volume)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    condition_id,
                    datetime.now().isoformat(),
                    yes_price,
                    no_price,
                    volume,
                )
            )
            await db.commit()

    async def record_trade(
        self,
        market_id: str,
        outcome: str,
        side: str,
        size: float,
        price: float,
        pnl: float = 0.0,
        agent_name: Optional[str] = None,
        strategy: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> None:
        """Record a trade."""
        if not self._initialized:
            await self.initialize()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO trade_history
                (market_id, outcome, side, size, price, pnl, timestamp, agent_name, strategy, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    market_id,
                    outcome,
                    side,
                    size,
                    price,
                    pnl,
                    datetime.now().isoformat(),
                    agent_name,
                    strategy,
                    json.dumps(metadata) if metadata else None,
                )
            )
            await db.commit()

    async def get_price_history(
        self,
        condition_id: str,
        days: int = 30,
        interval_minutes: int = 60,
    ) -> List[PricePoint]:
        """
        Get price history for a market.

        Args:
            condition_id: Market condition ID
            days: Number of days of history
            interval_minutes: Aggregation interval

        Returns:
            List of PricePoint objects
        """
        if not self._initialized:
            await self.initialize()

        start_time = datetime.now() - timedelta(days=days)

        async with aiosqlite.connect(self.db_path) as db:
            # Get raw data first
            cursor = await db.execute(
                """
                SELECT condition_id, timestamp, yes_price, no_price, volume
                FROM price_points
                WHERE condition_id = ? AND timestamp >= ?
                ORDER BY timestamp ASC
                """,
                (condition_id, start_time.isoformat())
            )

            rows = await cursor.fetchall()

            # Also check snapshots
            cursor = await db.execute(
                """
                SELECT condition_id, timestamp, yes_price, no_price, volume
                FROM market_snapshots
                WHERE condition_id = ? AND timestamp >= ?
                ORDER BY timestamp ASC
                """,
                (condition_id, start_time.isoformat())
            )

            snapshot_rows = await cursor.fetchall()

        # Combine and sort
        all_data = list(rows) + list(snapshot_rows)
        all_data.sort(key=lambda x: x[1])

        # Convert to PricePoints
        points = []
        for row in all_data:
            points.append(PricePoint(
                condition_id=row[0],
                timestamp=datetime.fromisoformat(row[1]) if isinstance(row[1], str) else row[1],
                yes_price=row[2],
                no_price=row[3],
                volume=row[4] or 0.0,
            ))

        return points

    async def get_snapshots(
        self,
        condition_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[MarketSnapshot]:
        """
        Get market snapshots.

        Args:
            condition_id: Filter by market (optional)
            start_time: Start of time range
            end_time: End of time range
            limit: Maximum results

        Returns:
            List of MarketSnapshot objects
        """
        if not self._initialized:
            await self.initialize()

        query = "SELECT * FROM market_snapshots WHERE 1=1"
        params = []

        if condition_id:
            query += " AND condition_id = ?"
            params.append(condition_id)

        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time.isoformat())

        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time.isoformat())

        query += f" ORDER BY timestamp DESC LIMIT {limit}"

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()

        snapshots = []
        for row in rows:
            snapshots.append(MarketSnapshot(
                condition_id=row["condition_id"],
                question=row["question"] or "",
                timestamp=datetime.fromisoformat(row["timestamp"]) if isinstance(row["timestamp"], str) else row["timestamp"],
                yes_price=row["yes_price"],
                no_price=row["no_price"],
                volume=row["volume"] or 0.0,
                liquidity=row["liquidity"] or 0.0,
                metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            ))

        return snapshots

    async def get_trade_history(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        agent_name: Optional[str] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Get trade history."""
        if not self._initialized:
            await self.initialize()

        query = "SELECT * FROM trade_history WHERE 1=1"
        params = []

        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time.isoformat())

        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time.isoformat())

        if agent_name:
            query += " AND agent_name = ?"
            params.append(agent_name)

        query += f" ORDER BY timestamp DESC LIMIT {limit}"

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()

        return [dict(row) for row in rows]

    async def get_ohlc(
        self,
        condition_id: str,
        interval: str = "1h",
        days: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Get OHLC (Open-High-Low-Close) data.

        Args:
            condition_id: Market condition ID
            interval: Time interval (1h, 4h, 1d)
            days: Number of days

        Returns:
            List of OHLC candles
        """
        history = await self.get_price_history(condition_id, days)

        if not history:
            return []

        # Parse interval
        if interval == "1h":
            interval_td = timedelta(hours=1)
        elif interval == "4h":
            interval_td = timedelta(hours=4)
        elif interval == "1d":
            interval_td = timedelta(days=1)
        else:
            interval_td = timedelta(hours=1)

        # Group by interval
        candles = []
        current_candle = None

        for point in history:
            candle_start = point.timestamp.replace(
                minute=0, second=0, microsecond=0
            )

            if current_candle is None or point.timestamp >= current_candle["close_time"]:
                # Start new candle
                if current_candle:
                    candles.append(current_candle)

                current_candle = {
                    "open_time": candle_start,
                    "close_time": candle_start + interval_td,
                    "open": point.yes_price,
                    "high": point.yes_price,
                    "low": point.yes_price,
                    "close": point.yes_price,
                    "volume": point.volume,
                }
            else:
                # Update current candle
                current_candle["high"] = max(current_candle["high"], point.yes_price)
                current_candle["low"] = min(current_candle["low"], point.yes_price)
                current_candle["close"] = point.yes_price
                current_candle["volume"] += point.volume

        if current_candle:
            candles.append(current_candle)

        return candles

    async def cleanup_old_data(self) -> int:
        """
        Remove data older than retention period.

        Returns:
            Number of rows deleted
        """
        if not self._initialized:
            await self.initialize()

        cutoff = datetime.now() - timedelta(days=self.retention_days)
        total_deleted = 0

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM market_snapshots WHERE timestamp < ?",
                (cutoff.isoformat(),)
            )
            total_deleted += cursor.rowcount

            cursor = await db.execute(
                "DELETE FROM price_points WHERE timestamp < ?",
                (cutoff.isoformat(),)
            )
            total_deleted += cursor.rowcount

            await db.commit()

        if total_deleted > 0:
            logger.info(f"[HistoricalDataStore] Cleaned up {total_deleted} old records")

        return total_deleted

    async def get_stats(self) -> Dict[str, Any]:
        """Get storage statistics."""
        if not self._initialized:
            await self.initialize()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM market_snapshots")
            snapshot_count = (await cursor.fetchone())[0]

            cursor = await db.execute("SELECT COUNT(*) FROM price_points")
            price_count = (await cursor.fetchone())[0]

            cursor = await db.execute("SELECT COUNT(*) FROM trade_history")
            trade_count = (await cursor.fetchone())[0]

            cursor = await db.execute(
                "SELECT COUNT(DISTINCT condition_id) FROM market_snapshots"
            )
            market_count = (await cursor.fetchone())[0]

        return {
            "db_path": self.db_path,
            "snapshots": snapshot_count,
            "price_points": price_count,
            "trades": trade_count,
            "unique_markets": market_count,
            "retention_days": self.retention_days,
        }


# Global instance
_historical_store: Optional[HistoricalDataStore] = None


async def get_historical_store() -> HistoricalDataStore:
    """Get or create the global historical data store."""
    global _historical_store

    if _historical_store is None:
        _historical_store = HistoricalDataStore()
        await _historical_store.initialize()

    return _historical_store
