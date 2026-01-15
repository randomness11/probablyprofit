"""
Tests for cache thread safety using TTLCache.
"""

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest


class TestTTLCacheThreadSafety:
    """Tests for thread-safe TTLCache operations."""

    def test_concurrent_get_set(self):
        """Test concurrent get and set operations."""
        from probablyprofit.utils.cache import TTLCache

        cache = TTLCache(ttl=60.0, max_size=100, name="test_concurrent")
        errors = []

        def writer(n):
            try:
                for i in range(50):
                    cache.set(f"key_{n}_{i}", f"value_{n}_{i}")
            except Exception as e:
                errors.append(e)

        def reader(n):
            try:
                for i in range(50):
                    cache.get(f"key_{n}_{i}")
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(5):
            threads.append(threading.Thread(target=writer, args=(i,)))
            threads.append(threading.Thread(target=reader, args=(i,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_concurrent_delete(self):
        """Test concurrent delete operations."""
        from probablyprofit.utils.cache import TTLCache

        cache = TTLCache(ttl=60.0, max_size=200, name="test_delete")

        # Pre-populate cache
        for i in range(100):
            cache.set(f"key_{i}", f"value_{i}")

        errors = []

        def deleter(start):
            try:
                for i in range(start, start + 20):
                    cache.delete(f"key_{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=deleter, args=(i * 20,)) for i in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_concurrent_clear(self):
        """Test concurrent clear operations."""
        from probablyprofit.utils.cache import TTLCache

        cache = TTLCache(ttl=60.0, max_size=200, name="test_clear")
        errors = []

        def writer():
            try:
                for i in range(100):
                    cache.set(f"key_{i}", f"value_{i}")
            except Exception as e:
                errors.append(e)

        def clearer():
            try:
                time.sleep(0.01)  # Small delay
                cache.clear()
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=clearer),
            threading.Thread(target=writer),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_lock_exists(self):
        """Test that cache has a thread lock."""
        from probablyprofit.utils.cache import TTLCache

        cache = TTLCache(name="test_lock")

        assert hasattr(cache, "_thread_lock")


class TestAsyncTTLCacheOperations:
    """Tests for async AsyncTTLCache operations."""

    @pytest.mark.asyncio
    async def test_async_get_set(self):
        """Test async get and set operations."""
        from probablyprofit.utils.cache import AsyncTTLCache

        cache = AsyncTTLCache(ttl=60.0, name="test_async")

        await cache.set_async("key1", "value1")
        result = await cache.get_async("key1")

        assert result == "value1"

    @pytest.mark.asyncio
    async def test_async_delete(self):
        """Test async delete operation."""
        from probablyprofit.utils.cache import AsyncTTLCache

        cache = AsyncTTLCache(ttl=60.0, name="test_async_delete")

        await cache.set_async("key1", "value1")
        await cache.delete_async("key1")
        result = await cache.get_async("key1")

        assert result is None

    @pytest.mark.asyncio
    async def test_concurrent_async_operations(self):
        """Test concurrent async operations."""
        from probablyprofit.utils.cache import AsyncTTLCache

        cache = AsyncTTLCache(ttl=60.0, max_size=200, name="test_concurrent_async")
        errors = []

        async def writer(n):
            try:
                for i in range(20):
                    await cache.set_async(f"async_key_{n}_{i}", f"value_{n}_{i}")
            except Exception as e:
                errors.append(e)

        async def reader(n):
            try:
                for i in range(20):
                    await cache.get_async(f"async_key_{n}_{i}")
            except Exception as e:
                errors.append(e)

        tasks = []
        for i in range(5):
            tasks.append(writer(i))
            tasks.append(reader(i))

        await asyncio.gather(*tasks)

        assert len(errors) == 0


class TestAgentMemoryThreadSafety:
    """Tests for agent memory thread safety."""

    @pytest.mark.asyncio
    async def test_concurrent_add_observation(self):
        """Test concurrent observation additions."""
        from probablyprofit.agent.base import AgentMemory

        memory = AgentMemory()
        errors = []

        async def add_observations(n):
            try:
                for i in range(20):
                    await memory.add_observation(f"Observation {n}_{i}")
            except Exception as e:
                errors.append(e)

        tasks = [add_observations(i) for i in range(5)]
        await asyncio.gather(*tasks)

        assert len(errors) == 0
        assert len(memory.observations) == 100  # 5 * 20

    @pytest.mark.asyncio
    async def test_concurrent_add_decision(self):
        """Test concurrent decision additions."""
        from probablyprofit.agent.base import AgentMemory, Decision

        memory = AgentMemory()
        errors = []

        async def add_decisions(n):
            try:
                for i in range(20):
                    decision = Decision(
                        action="hold",
                        reasoning=f"Decision {n}_{i}",
                        confidence=0.5 + i * 0.01,
                    )
                    await memory.add_decision(decision)
            except Exception as e:
                errors.append(e)

        tasks = [add_decisions(i) for i in range(5)]
        await asyncio.gather(*tasks)

        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_memory_lock_exists(self):
        """Test that AgentMemory has an async lock."""
        from probablyprofit.agent.base import AgentMemory

        memory = AgentMemory()

        assert hasattr(memory, "_lock")
        assert isinstance(memory._lock, asyncio.Lock)


class TestTTLCacheEviction:
    """Tests for cache eviction under concurrent access."""

    def test_max_size_respected(self):
        """Test that max_size is respected."""
        from probablyprofit.utils.cache import TTLCache

        cache = TTLCache(ttl=60.0, max_size=50, name="test_eviction")

        # Add more items than max_size
        for i in range(100):
            cache.set(f"key_{i}", f"value_{i}")

        # Cache size should not exceed max_size
        assert cache.size <= 50

    def test_ttl_expiration(self):
        """Test that TTL expiration works."""
        from probablyprofit.utils.cache import TTLCache

        cache = TTLCache(ttl=0.1, name="test_ttl")  # 100ms TTL

        cache.set("key", "value")
        assert cache.get("key") == "value"

        # Wait for TTL to expire
        time.sleep(0.15)

        # Should be expired now
        assert cache.get("key") is None


class TestTTLCacheStats:
    """Tests for cache statistics."""

    def test_hit_miss_tracking(self):
        """Test that hits and misses are tracked."""
        from probablyprofit.utils.cache import TTLCache

        cache = TTLCache(ttl=60.0, name="test_stats")

        # Set and get (hit)
        cache.set("key", "value")
        cache.get("key")

        # Miss
        cache.get("nonexistent")

        stats = cache.stats
        assert stats["hits"] >= 1
        assert stats["misses"] >= 1
