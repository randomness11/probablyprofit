"""
Resilience utilities for probablyprofit.

Provides retry logic, circuit breakers, and rate limiting
to make the bot bulletproof against API failures.
"""

import asyncio
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Any, Callable, Optional, Set, Type, TypeVar, Union

from loguru import logger

from probablyprofit.api.exceptions import APIException, NetworkException, RateLimitException

# Type variable for generic return types
T = TypeVar("T")


# =============================================================================
# RETRY WITH EXPONENTIAL BACKOFF
# =============================================================================


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_attempts: int = 3
    base_delay: float = 1.0  # seconds
    max_delay: float = 60.0  # seconds
    exponential_base: float = 2.0
    jitter: bool = True  # Add randomness to prevent thundering herd

    # Exceptions that should trigger a retry
    retryable_exceptions: tuple = (
        NetworkException,
        RateLimitException,
        ConnectionError,
        TimeoutError,
        asyncio.TimeoutError,
    )

    # Exceptions that should NOT be retried (fail fast)
    non_retryable_exceptions: tuple = (
        ValueError,
        TypeError,
        KeyError,
    )


def calculate_delay(attempt: int, config: RetryConfig) -> float:
    """
    Calculate delay before next retry using exponential backoff.

    Args:
        attempt: Current attempt number (0-indexed)
        config: Retry configuration

    Returns:
        Delay in seconds
    """
    delay = config.base_delay * (config.exponential_base**attempt)
    delay = min(delay, config.max_delay)

    if config.jitter:
        # Add up to 25% jitter
        jitter_range = delay * 0.25
        delay += random.uniform(-jitter_range, jitter_range)
        delay = max(0.1, delay)  # Ensure positive delay

    return delay


def retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    retryable_exceptions: Optional[tuple] = None,
    on_retry: Optional[Callable[[Exception, int], None]] = None,
) -> Callable:
    """
    Decorator for retrying async functions with exponential backoff.

    Args:
        max_attempts: Maximum number of attempts
        base_delay: Initial delay between retries
        max_delay: Maximum delay between retries
        retryable_exceptions: Tuple of exceptions to retry on
        on_retry: Optional callback called before each retry

    Usage:
        @retry(max_attempts=3, base_delay=1.0)
        async def fetch_data():
            ...
    """
    config = RetryConfig(
        max_attempts=max_attempts,
        base_delay=base_delay,
        max_delay=max_delay,
    )

    if retryable_exceptions:
        config.retryable_exceptions = retryable_exceptions

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Optional[Exception] = None

            for attempt in range(config.max_attempts):
                try:
                    return await func(*args, **kwargs)

                except config.non_retryable_exceptions as e:
                    # Don't retry these - fail fast
                    logger.error(f"[Retry] Non-retryable error in {func.__name__}: {e}")
                    raise

                except config.retryable_exceptions as e:
                    last_exception = e

                    if attempt < config.max_attempts - 1:
                        delay = calculate_delay(attempt, config)
                        logger.warning(
                            f"[Retry] {func.__name__} failed (attempt {attempt + 1}/{config.max_attempts}): {e}. "
                            f"Retrying in {delay:.2f}s..."
                        )

                        if on_retry:
                            on_retry(e, attempt)

                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"[Retry] {func.__name__} failed after {config.max_attempts} attempts: {e}"
                        )

                except Exception as e:
                    # Unknown exception - log and retry if it looks transient
                    last_exception = e

                    if attempt < config.max_attempts - 1:
                        delay = calculate_delay(attempt, config)
                        logger.warning(
                            f"[Retry] Unexpected error in {func.__name__} (attempt {attempt + 1}): {e}. "
                            f"Retrying in {delay:.2f}s..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"[Retry] {func.__name__} failed with unexpected error: {e}")
                        raise

            # All retries exhausted
            if last_exception:
                raise last_exception
            raise RuntimeError(f"Retry exhausted for {func.__name__}")

        return wrapper

    return decorator


# =============================================================================
# CIRCUIT BREAKER
# =============================================================================


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, rejecting calls
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 2  # Successes to close from half-open
    timeout: float = 30.0  # Seconds before trying half-open

    # Exceptions that count as failures
    failure_exceptions: tuple = (
        NetworkException,
        RateLimitException,
        ConnectionError,
        TimeoutError,
        asyncio.TimeoutError,
        APIException,
    )


class CircuitBreaker:
    """
    Circuit breaker to prevent cascading failures.

    When a service fails repeatedly, the circuit "opens" and rejects
    calls immediately instead of waiting for timeouts.

    Usage:
        breaker = CircuitBreaker("polymarket-api")

        @breaker
        async def call_api():
            ...
    """

    # Class-level registry of all circuit breakers
    _breakers: dict = {}

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout: float = 30.0,
    ):
        self.name = name
        self.config = CircuitBreakerConfig(
            failure_threshold=failure_threshold,
            success_threshold=success_threshold,
            timeout=timeout,
        )

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._lock = asyncio.Lock()

        # Register this breaker
        CircuitBreaker._breakers[name] = self

        logger.debug(f"[CircuitBreaker] '{name}' initialized (threshold: {failure_threshold})")

    @property
    def state(self) -> CircuitState:
        """Get current state, potentially transitioning from OPEN to HALF_OPEN."""
        if self._state == CircuitState.OPEN:
            if (
                self._last_failure_time
                and (time.time() - self._last_failure_time) >= self.config.timeout
            ):
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
                logger.info(f"[CircuitBreaker] '{self.name}' transitioning to HALF_OPEN")
        return self._state

    @property
    def is_closed(self) -> bool:
        return self.state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    async def _record_success(self) -> None:
        """Record a successful call."""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    logger.info(f"[CircuitBreaker] '{self.name}' CLOSED (service recovered)")
            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success
                self._failure_count = 0

    async def _record_failure(self, exception: Exception) -> None:
        """Record a failed call."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                # Single failure in half-open returns to open
                self._state = CircuitState.OPEN
                logger.warning(f"[CircuitBreaker] '{self.name}' OPEN (failed in half-open)")

            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.config.failure_threshold:
                    self._state = CircuitState.OPEN
                    logger.warning(
                        f"[CircuitBreaker] '{self.name}' OPEN " f"({self._failure_count} failures)"
                    )

    def reset(self) -> None:
        """Manually reset the circuit breaker."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None
        logger.info(f"[CircuitBreaker] '{self.name}' manually reset")

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        """Decorator to wrap a function with circuit breaker logic."""

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            # Check if circuit is open
            if self.state == CircuitState.OPEN:
                raise APIException(f"Circuit breaker '{self.name}' is OPEN - service unavailable")

            try:
                result = await func(*args, **kwargs)
                await self._record_success()
                return result

            except self.config.failure_exceptions as e:
                await self._record_failure(e)
                raise

            except Exception as e:
                # Don't count other exceptions as circuit failures
                raise

        return wrapper

    @classmethod
    def get(cls, name: str) -> Optional["CircuitBreaker"]:
        """Get a circuit breaker by name."""
        return cls._breakers.get(name)

    @classmethod
    def get_all_states(cls) -> dict:
        """Get states of all circuit breakers."""
        return {name: breaker.state.value for name, breaker in cls._breakers.items()}


# =============================================================================
# RATE LIMITER
# =============================================================================


@dataclass
class RateLimiterConfig:
    """Configuration for rate limiter."""

    calls: int = 10  # Number of calls allowed
    period: float = 1.0  # Time period in seconds
    burst: int = 0  # Extra calls allowed in burst (0 = no burst)


class RateLimiter:
    """
    Token bucket rate limiter.

    Limits the number of calls to a function within a time period.

    Usage:
        limiter = RateLimiter("api-calls", calls=10, period=1.0)

        @limiter
        async def call_api():
            ...
    """

    def __init__(
        self,
        name: str,
        calls: int = 10,
        period: float = 1.0,
        burst: int = 0,
    ):
        self.name = name
        self.config = RateLimiterConfig(calls=calls, period=period, burst=burst)

        self._tokens = float(calls + burst)
        self._max_tokens = float(calls + burst)
        self._last_update = time.time()
        self._lock = asyncio.Lock()

        logger.debug(f"[RateLimiter] '{name}' initialized ({calls} calls/{period}s)")

    async def acquire(self, tokens: int = 1) -> float:
        """
        Acquire tokens, waiting if necessary.

        Args:
            tokens: Number of tokens to acquire

        Returns:
            Wait time in seconds (0 if no wait needed)
        """
        async with self._lock:
            now = time.time()

            # Refill tokens based on elapsed time
            elapsed = now - self._last_update
            refill = elapsed * (self.config.calls / self.config.period)
            self._tokens = min(self._max_tokens, self._tokens + refill)
            self._last_update = now

            if self._tokens >= tokens:
                self._tokens -= tokens
                return 0.0

            # Calculate wait time
            tokens_needed = tokens - self._tokens
            wait_time = tokens_needed * (self.config.period / self.config.calls)

            return wait_time

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        """Decorator to wrap a function with rate limiting."""

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            wait_time = await self.acquire()

            if wait_time > 0:
                logger.debug(f"[RateLimiter] '{self.name}' waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
                # Re-acquire after waiting
                await self.acquire()

            return await func(*args, **kwargs)

        return wrapper


# =============================================================================
# COMBINED RESILIENCE DECORATOR
# =============================================================================


def resilient(
    retry_attempts: int = 3,
    retry_delay: float = 1.0,
    circuit_breaker: Optional[str] = None,
    rate_limit_calls: Optional[int] = None,
    rate_limit_period: float = 1.0,
) -> Callable:
    """
    Combined decorator for retry + circuit breaker + rate limiting.

    Args:
        retry_attempts: Max retry attempts
        retry_delay: Base delay between retries
        circuit_breaker: Name of circuit breaker to use (creates if doesn't exist)
        rate_limit_calls: Max calls per period (None to disable)
        rate_limit_period: Rate limit period in seconds

    Usage:
        @resilient(retry_attempts=3, circuit_breaker="polymarket")
        async def fetch_markets():
            ...
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        # Build the decoration chain
        decorated = func

        # Apply rate limiter (innermost)
        if rate_limit_calls:
            limiter = RateLimiter(
                f"{func.__name__}-limiter",
                calls=rate_limit_calls,
                period=rate_limit_period,
            )
            decorated = limiter(decorated)

        # Apply circuit breaker (middle)
        if circuit_breaker:
            breaker = CircuitBreaker.get(circuit_breaker)
            if not breaker:
                breaker = CircuitBreaker(circuit_breaker)
            decorated = breaker(decorated)

        # Apply retry (outermost)
        if retry_attempts > 1:
            decorated = retry(
                max_attempts=retry_attempts,
                base_delay=retry_delay,
            )(decorated)

        return decorated

    return decorator


# =============================================================================
# TIMEOUT WRAPPER
# =============================================================================


def with_timeout(seconds: float) -> Callable:
    """
    Decorator to add timeout to async functions.

    Args:
        seconds: Timeout in seconds

    Usage:
        @with_timeout(30.0)
        async def slow_operation():
            ...
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=seconds)
            except asyncio.TimeoutError:
                logger.error(f"[Timeout] {func.__name__} timed out after {seconds}s")
                raise

        return wrapper

    return decorator


# =============================================================================
# HEALTH CHECK UTILITIES
# =============================================================================


def get_resilience_status() -> dict:
    """Get status of all resilience components."""
    return {
        "circuit_breakers": CircuitBreaker.get_all_states(),
    }


def reset_all_circuit_breakers() -> None:
    """Reset all circuit breakers to closed state."""
    for breaker in CircuitBreaker._breakers.values():
        breaker.reset()
    logger.info("[Resilience] All circuit breakers reset")
