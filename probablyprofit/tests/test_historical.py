"""
Tests for Historical Data Storage.
"""
import pytest
import asyncio
import tempfile
import os
from datetime import datetime, timedelta

# Skip if aiosqlite not available
pytest.importorskip("aiosqlite")

from probablyprofit.storage.historical import (
    HistoricalDataStore,
    MarketSnapshot,
    PricePoint,
)


@pytest.fixture
async def store():
    """Create a temporary historical data store."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    store = HistoricalDataStore(db_path=db_path)
    await store.initialize()
    yield store

    # Cleanup
    os.unlink(db_path)


class TestHistoricalDataStore:
    """Tests for HistoricalDataStore."""

    @pytest.mark.asyncio
    async def test_initialize(self, store):
        assert store._initialized is True

    @pytest.mark.asyncio
    async def test_record_snapshot(self, store):
        await store.record_snapshot(
            condition_id="0x123",
            question="Will it happen?",
            yes_price=0.65,
            no_price=0.35,
            volume=10000,
            liquidity=5000,
        )

        snapshots = await store.get_snapshots(condition_id="0x123")
        assert len(snapshots) == 1
        assert snapshots[0].condition_id == "0x123"
        assert snapshots[0].yes_price == 0.65

    @pytest.mark.asyncio
    async def test_record_price(self, store):
        await store.record_price(
            condition_id="0x123",
            yes_price=0.60,
            no_price=0.40,
            volume=100,
        )

        history = await store.get_price_history("0x123", days=1)
        assert len(history) >= 1

    @pytest.mark.asyncio
    async def test_record_trade(self, store):
        await store.record_trade(
            market_id="0x123",
            outcome="Yes",
            side="BUY",
            size=100.0,
            price=0.5,
            pnl=10.0,
            agent_name="TestAgent",
            strategy="momentum",
        )

        trades = await store.get_trade_history()
        assert len(trades) == 1
        assert trades[0]["market_id"] == "0x123"
        assert trades[0]["pnl"] == 10.0

    @pytest.mark.asyncio
    async def test_get_snapshots_filtered(self, store):
        # Add multiple snapshots
        await store.record_snapshot("0x123", "Market 1", 0.5, 0.5, 100, 50)
        await store.record_snapshot("0x456", "Market 2", 0.6, 0.4, 200, 100)
        await store.record_snapshot("0x123", "Market 1", 0.55, 0.45, 150, 75)

        # Filter by condition_id
        snapshots = await store.get_snapshots(condition_id="0x123")
        assert len(snapshots) == 2
        assert all(s.condition_id == "0x123" for s in snapshots)

    @pytest.mark.asyncio
    async def test_get_price_history(self, store):
        # Add price points
        for i in range(10):
            await store.record_price(
                condition_id="0x123",
                yes_price=0.5 + i * 0.01,
                no_price=0.5 - i * 0.01,
                volume=float(i * 100),
            )

        history = await store.get_price_history("0x123", days=30)
        assert len(history) == 10

    @pytest.mark.asyncio
    async def test_get_ohlc(self, store):
        # Add some price points
        for i in range(5):
            await store.record_price(
                condition_id="0x123",
                yes_price=0.5 + i * 0.02,
                no_price=0.5 - i * 0.02,
            )

        ohlc = await store.get_ohlc("0x123", interval="1h", days=1)
        # Should have at least 1 candle
        assert len(ohlc) >= 1

    @pytest.mark.asyncio
    async def test_get_stats(self, store):
        await store.record_snapshot("0x123", "Test", 0.5, 0.5, 100, 50)
        await store.record_price("0x123", 0.5, 0.5)
        await store.record_trade("0x123", "Yes", "BUY", 10, 0.5)

        stats = await store.get_stats()
        assert stats["snapshots"] >= 1
        assert stats["price_points"] >= 1
        assert stats["trades"] >= 1

    @pytest.mark.asyncio
    async def test_cleanup_old_data(self, store):
        # This just verifies the method runs without error
        deleted = await store.cleanup_old_data()
        assert deleted >= 0

    @pytest.mark.asyncio
    async def test_metadata_json(self, store):
        await store.record_snapshot(
            condition_id="0x123",
            question="Test",
            yes_price=0.5,
            no_price=0.5,
            metadata={"source": "test", "extra": 123},
        )

        snapshots = await store.get_snapshots(condition_id="0x123")
        assert snapshots[0].metadata["source"] == "test"


class TestPricePoint:
    """Tests for PricePoint dataclass."""

    def test_creation(self):
        point = PricePoint(
            condition_id="0x123",
            timestamp=datetime.now(),
            yes_price=0.6,
            no_price=0.4,
            volume=1000,
        )
        assert point.condition_id == "0x123"
        assert point.yes_price == 0.6


class TestMarketSnapshot:
    """Tests for MarketSnapshot dataclass."""

    def test_creation(self):
        snapshot = MarketSnapshot(
            condition_id="0x123",
            question="Will it happen?",
            timestamp=datetime.now(),
            yes_price=0.65,
            no_price=0.35,
            volume=10000,
            liquidity=5000,
        )
        assert snapshot.condition_id == "0x123"
        assert snapshot.question == "Will it happen?"
