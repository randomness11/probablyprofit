"""
Tests for TTL Cache utilities.
"""
import pytest
import asyncio
import time

from probablyprofit.utils.cache import TTLCache, AsyncTTLCache, cached


class TestTTLCache:
    """Tests for TTLCache."""

    def test_basic_set_get(self):
        cache = TTLCache(ttl=60.0, name="test")
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_nonexistent(self):
        cache = TTLCache(ttl=60.0)
        assert cache.get("nonexistent") is None

    def test_expiration(self):
        cache = TTLCache(ttl=0.1)  # 100ms TTL
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

        time.sleep(0.15)  # Wait for expiration
        assert cache.get("key1") is None

    def test_custom_ttl_per_key(self):
        cache = TTLCache(ttl=60.0)
        cache.set("short", "value", ttl=0.1)
        cache.set("long", "value", ttl=60.0)

        time.sleep(0.15)
        assert cache.get("short") is None
        assert cache.get("long") == "value"

    def test_max_size_eviction(self):
        cache = TTLCache(ttl=60.0, max_size=3)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        cache.set("key4", "value4")  # Should evict key1

        assert cache.size == 3
        # Oldest key should be evicted
        assert cache.get("key1") is None

    def test_delete(self):
        cache = TTLCache(ttl=60.0)
        cache.set("key1", "value1")
        assert cache.delete("key1") is True
        assert cache.get("key1") is None
        assert cache.delete("nonexistent") is False

    def test_clear(self):
        cache = TTLCache(ttl=60.0)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        count = cache.clear()
        assert count == 2
        assert cache.size == 0

    def test_contains(self):
        cache = TTLCache(ttl=60.0)
        cache.set("key1", "value1")
        assert "key1" in cache
        assert "nonexistent" not in cache

    def test_stats(self):
        cache = TTLCache(ttl=60.0, max_size=10, name="test-stats")
        cache.set("key1", "value1")
        cache.get("key1")  # hit
        cache.get("key1")  # hit
        cache.get("nonexistent")  # miss

        stats = cache.stats
        assert stats["name"] == "test-stats"
        assert stats["size"] == 1
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate"] == pytest.approx(2/3, rel=0.01)

    def test_cleanup_expired(self):
        cache = TTLCache(ttl=0.1)
        cache.set("key1", "value1")
        cache.set("key2", "value2")

        time.sleep(0.15)
        removed = cache.cleanup_expired()
        assert removed == 2
        assert cache.size == 0


class TestAsyncTTLCache:
    """Tests for AsyncTTLCache."""

    @pytest.mark.asyncio
    async def test_async_get_set(self):
        cache = AsyncTTLCache(ttl=60.0)
        await cache.set_async("key1", "value1")
        result = await cache.get_async("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_async_delete(self):
        cache = AsyncTTLCache(ttl=60.0)
        await cache.set_async("key1", "value1")
        deleted = await cache.delete_async("key1")
        assert deleted is True
        result = await cache.get_async("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_or_set(self):
        cache = AsyncTTLCache(ttl=60.0)
        call_count = [0]

        def factory():
            call_count[0] += 1
            return "computed_value"

        # First call should compute
        result1 = await cache.get_or_set("key1", factory)
        assert result1 == "computed_value"
        assert call_count[0] == 1

        # Second call should use cache
        result2 = await cache.get_or_set("key1", factory)
        assert result2 == "computed_value"
        assert call_count[0] == 1  # Not called again

    @pytest.mark.asyncio
    async def test_get_or_set_async_factory(self):
        cache = AsyncTTLCache(ttl=60.0)

        async def async_factory():
            await asyncio.sleep(0.01)
            return "async_value"

        result = await cache.get_or_set("key1", async_factory)
        assert result == "async_value"


class TestCachedDecorator:
    """Tests for @cached decorator."""

    @pytest.mark.asyncio
    async def test_cached_function(self):
        call_count = [0]

        @cached(ttl=60.0)
        async def expensive_function(x: int) -> int:
            call_count[0] += 1
            return x * 2

        # First call
        result1 = await expensive_function(5)
        assert result1 == 10
        assert call_count[0] == 1

        # Second call with same arg should use cache
        result2 = await expensive_function(5)
        assert result2 == 10
        assert call_count[0] == 1

        # Different arg should call function
        result3 = await expensive_function(10)
        assert result3 == 20
        assert call_count[0] == 2

    @pytest.mark.asyncio
    async def test_cached_with_custom_key(self):
        @cached(ttl=60.0, key_builder=lambda x, y: f"{x}-{y}")
        async def add(x: int, y: int) -> int:
            return x + y

        result = await add(1, 2)
        assert result == 3

        # Access cache stats
        assert hasattr(add, 'cache')
        assert add.cache.size == 1
