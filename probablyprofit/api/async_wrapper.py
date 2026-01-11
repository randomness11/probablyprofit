"""
Async Wrapper Utilities

Provides utilities to safely wrap synchronous libraries in async contexts.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from typing import Callable, TypeVar, Any
from loguru import logger


T = TypeVar("T")

# Thread pool for running sync operations
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="sync-wrapper")


async def run_sync(func: Callable[..., T], *args, **kwargs) -> T:
    """
    Run a synchronous function in a thread pool.

    This is the safe way to call synchronous blocking code
    from an async context without blocking the event loop.

    Args:
        func: Synchronous function to call
        *args: Positional arguments
        **kwargs: Keyword arguments

    Returns:
        Result of the function call

    Usage:
        result = await run_sync(sync_client.get_balance)
        result = await run_sync(sync_client.create_order, order_args)
    """
    loop = asyncio.get_event_loop()

    # Create a partial function with kwargs if needed
    if kwargs:
        from functools import partial
        func = partial(func, **kwargs)
        result = await loop.run_in_executor(_executor, func, *args)
    else:
        result = await loop.run_in_executor(_executor, func, *args)

    return result


def async_wrap(func: Callable[..., T]) -> Callable[..., T]:
    """
    Decorator to wrap a synchronous function for async use.

    Usage:
        @async_wrap
        def sync_function():
            return slow_blocking_call()

        # Now can be called with await
        result = await sync_function()
    """
    @wraps(func)
    async def wrapper(*args, **kwargs) -> T:
        return await run_sync(func, *args, **kwargs)

    return wrapper


class AsyncClientWrapper:
    """
    Wrapper to make a synchronous client work in async contexts.

    Automatically wraps all method calls to run in a thread pool.

    Usage:
        sync_client = ClobClient(...)
        async_client = AsyncClientWrapper(sync_client)

        # Now safe to await
        result = await async_client.create_order(args)
    """

    def __init__(self, sync_client: Any, timeout: float = 30.0):
        """
        Initialize wrapper.

        Args:
            sync_client: The synchronous client to wrap
            timeout: Timeout for each operation in seconds
        """
        self._sync_client = sync_client
        self._timeout = timeout

    def __getattr__(self, name: str):
        """Wrap attribute access to handle method calls."""
        attr = getattr(self._sync_client, name)

        if callable(attr):
            @wraps(attr)
            async def async_method(*args, **kwargs):
                try:
                    return await asyncio.wait_for(
                        run_sync(attr, *args, **kwargs),
                        timeout=self._timeout
                    )
                except asyncio.TimeoutError:
                    logger.error(f"[AsyncWrapper] {name}() timed out after {self._timeout}s")
                    raise
                except Exception as e:
                    logger.error(f"[AsyncWrapper] {name}() failed: {e}")
                    raise

            return async_method

        return attr


class SyncToAsyncMixin:
    """
    Mixin to add async versions of synchronous methods.

    Subclasses can mark methods with @sync_method decorator,
    and this mixin will automatically create async_* versions.

    Usage:
        class MyClient(SyncToAsyncMixin):
            def get_data(self) -> dict:
                return self._sync_call()

        client = MyClient()
        # Sync call
        data = client.get_data()
        # Async call
        data = await client.async_get_data()
    """

    def __getattr__(self, name: str):
        # Check if this is an async_* call for an existing method
        if name.startswith("async_"):
            sync_name = name[6:]  # Remove "async_" prefix
            if hasattr(self, sync_name):
                sync_method = getattr(self, sync_name)
                if callable(sync_method):
                    async def async_method(*args, **kwargs):
                        return await run_sync(sync_method, *args, **kwargs)
                    return async_method

        raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")


def sync_method(func: Callable[..., T]) -> Callable[..., T]:
    """
    Decorator to mark a method as having an automatic async version.

    Usage:
        class MyClient:
            @sync_method
            def get_balance(self) -> float:
                return self._sync_api_call()

        # Automatically creates async_get_balance()
    """
    func._is_sync_method = True
    return func


async def gather_with_concurrency(
    n: int,
    *coros,
    return_exceptions: bool = False,
):
    """
    Like asyncio.gather but limits concurrent tasks.

    Args:
        n: Maximum concurrent tasks
        *coros: Coroutines to run
        return_exceptions: Whether to return exceptions as results

    Returns:
        List of results

    Usage:
        results = await gather_with_concurrency(
            5,  # Max 5 concurrent
            fetch_market(m1),
            fetch_market(m2),
            fetch_market(m3),
            # ...many more...
        )
    """
    semaphore = asyncio.Semaphore(n)

    async def sem_coro(coro):
        async with semaphore:
            return await coro

    return await asyncio.gather(
        *(sem_coro(c) for c in coros),
        return_exceptions=return_exceptions,
    )


def shutdown_executor():
    """Shutdown the thread pool executor."""
    _executor.shutdown(wait=True)
    logger.info("[AsyncWrapper] Thread pool executor shutdown")
