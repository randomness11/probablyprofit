"""
TTL-based caching utilities for ProbablyProfit.

Provides in-memory caching with time-to-live expiration.
Thread-safe for both sync and async operations.
"""

import asyncio
import threading
import time
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable, Dict, Generic, Optional, TypeVar

from loguru import logger

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    """A single cache entry with TTL."""

    value: T
    expires_at: float
    created_at: float = field(default_factory=time.time)

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at


class TTLCache(Generic[T]):
    """
    Thread-safe TTL (Time-To-Live) cache.

    Features:
    - Automatic expiration of entries
    - Optional max size with LRU eviction
    - Statistics tracking
    - Async-compatible

    Usage:
        cache = TTLCache[Market](ttl=60.0, max_size=100)
        cache.set("market_123", market_obj)
        market = cache.get("market_123")
    """

    def __init__(
        self,
        ttl: float = 60.0,
        max_size: Optional[int] = None,
        name: str = "cache",
    ):
        """
        Initialize TTL cache.

        Args:
            ttl: Time-to-live in seconds
            max_size: Maximum number of entries (None for unlimited)
            name: Cache name for logging
        """
        self.ttl = ttl
        self.max_size = max_size
        self.name = name

        self._cache: Dict[str, CacheEntry[T]] = {}
        self._lock = asyncio.Lock()  # For async operations
        self._thread_lock = threading.RLock()  # For sync operations (reentrant)

        # Statistics
        self._hits = 0
        self._misses = 0
        self._evictions = 0

        logger.debug(f"[Cache] '{name}' initialized (TTL: {ttl}s, max_size: {max_size})")

    def get(self, key: str) -> Optional[T]:
        """
        Get a value from the cache (thread-safe).

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        with self._thread_lock:
            entry = self._cache.get(key)

            if entry is None:
                self._misses += 1
                return None

            if entry.is_expired:
                del self._cache[key]
                self._misses += 1
                return None

            self._hits += 1
            return entry.value

    def set(self, key: str, value: T, ttl: Optional[float] = None) -> None:
        """
        Set a value in the cache (thread-safe).

        Args:
            key: Cache key
            value: Value to cache
            ttl: Custom TTL for this entry (uses default if None)
        """
        with self._thread_lock:
            effective_ttl = ttl if ttl is not None else self.ttl

            # Evict if at max size
            if self.max_size and len(self._cache) >= self.max_size:
                self._evict_oldest_unsafe()

            self._cache[key] = CacheEntry(
                value=value,
                expires_at=time.time() + effective_ttl,
            )

    def delete(self, key: str) -> bool:
        """
        Delete a key from the cache (thread-safe).

        Args:
            key: Cache key

        Returns:
            True if key was deleted, False if not found
        """
        with self._thread_lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> int:
        """
        Clear all entries from the cache (thread-safe).

        Returns:
            Number of entries cleared
        """
        with self._thread_lock:
            count = len(self._cache)
            self._cache.clear()
            logger.debug(f"[Cache] '{self.name}' cleared ({count} entries)")
            return count

    def cleanup_expired(self) -> int:
        """
        Remove all expired entries (thread-safe).

        Returns:
            Number of entries removed
        """
        with self._thread_lock:
            expired_keys = [key for key, entry in self._cache.items() if entry.is_expired]

            for key in expired_keys:
                del self._cache[key]

            if expired_keys:
                logger.debug(f"[Cache] '{self.name}' cleaned up {len(expired_keys)} expired entries")

            return len(expired_keys)

    def _evict_oldest_unsafe(self) -> None:
        """Evict the oldest entry (LRU-style). Must be called with lock held."""
        if not self._cache:
            return

        oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k].created_at)
        del self._cache[oldest_key]
        self._evictions += 1

    @property
    def size(self) -> int:
        """Current number of entries."""
        return len(self._cache)

    @property
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_requests = self._hits + self._misses
        hit_rate = self._hits / total_requests if total_requests > 0 else 0.0

        return {
            "name": self.name,
            "size": self.size,
            "max_size": self.max_size,
            "ttl": self.ttl,
            "hits": self._hits,
            "misses": self._misses,
            "evictions": self._evictions,
            "hit_rate": hit_rate,
        }

    def __contains__(self, key: str) -> bool:
        """Check if key exists and is not expired (thread-safe)."""
        with self._thread_lock:
            entry = self._cache.get(key)
            if entry is None:
                return False
            if entry.is_expired:
                del self._cache[key]
                return False
            return True

    def __len__(self) -> int:
        return len(self._cache)


class AsyncTTLCache(TTLCache[T]):
    """
    Async-safe version of TTLCache.

    All operations are protected by an asyncio lock.
    """

    async def get_async(self, key: str) -> Optional[T]:
        """Async version of get."""
        async with self._lock:
            return self.get(key)

    async def set_async(self, key: str, value: T, ttl: Optional[float] = None) -> None:
        """Async version of set."""
        async with self._lock:
            self.set(key, value, ttl)

    async def delete_async(self, key: str) -> bool:
        """Async version of delete."""
        async with self._lock:
            return self.delete(key)

    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], T],
        ttl: Optional[float] = None,
    ) -> T:
        """
        Get value from cache, or compute and store it.

        Args:
            key: Cache key
            factory: Callable that returns the value if not cached
            ttl: Custom TTL

        Returns:
            Cached or newly computed value
        """
        async with self._lock:
            value = self.get(key)
            if value is not None:
                return value

            # Compute new value
            if asyncio.iscoroutinefunction(factory):
                value = await factory()
            else:
                value = factory()

            self.set(key, value, ttl)
            return value


def cached(
    ttl: float = 60.0,
    key_builder: Optional[Callable[..., str]] = None,
    cache_name: Optional[str] = None,
):
    """
    Decorator to cache function results.

    Args:
        ttl: Time-to-live in seconds
        key_builder: Function to build cache key from args
        cache_name: Name for the cache

    Usage:
        @cached(ttl=30.0)
        async def fetch_market(market_id: str) -> Market:
            ...
    """

    def decorator(func: Callable) -> Callable:
        func_cache = TTLCache(ttl=ttl, name=cache_name or func.__name__)

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Build cache key
            if key_builder:
                key = key_builder(*args, **kwargs)
            else:
                key = f"{args}:{kwargs}"

            # Check cache
            cached_value = func_cache.get(key)
            if cached_value is not None:
                logger.debug(f"[Cache] Hit for {func.__name__}({key})")
                return cached_value

            # Call function
            result = await func(*args, **kwargs)

            # Store in cache
            func_cache.set(key, result)
            logger.debug(f"[Cache] Miss for {func.__name__}({key}), stored result")

            return result

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            if key_builder:
                key = key_builder(*args, **kwargs)
            else:
                key = f"{args}:{kwargs}"

            cached_value = func_cache.get(key)
            if cached_value is not None:
                return cached_value

            result = func(*args, **kwargs)
            func_cache.set(key, result)
            return result

        # Attach cache for inspection
        wrapper = async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
        wrapper.cache = func_cache
        return wrapper

    return decorator


# =============================================================================
# GLOBAL CACHES
# =============================================================================

# Market data cache (60 second TTL)
market_cache: AsyncTTLCache = AsyncTTLCache(ttl=60.0, max_size=1000, name="markets")

# Price cache (10 second TTL - prices change frequently)
price_cache: AsyncTTLCache = AsyncTTLCache(ttl=10.0, max_size=500, name="prices")

# Order book cache (5 second TTL)
orderbook_cache: AsyncTTLCache = AsyncTTLCache(ttl=5.0, max_size=100, name="orderbooks")


def get_all_cache_stats() -> Dict[str, Dict[str, Any]]:
    """Get statistics for all global caches."""
    return {
        "markets": market_cache.stats,
        "prices": price_cache.stats,
        "orderbooks": orderbook_cache.stats,
    }


def clear_all_caches() -> Dict[str, int]:
    """Clear all global caches."""
    return {
        "markets": market_cache.clear(),
        "prices": price_cache.clear(),
        "orderbooks": orderbook_cache.clear(),
    }
