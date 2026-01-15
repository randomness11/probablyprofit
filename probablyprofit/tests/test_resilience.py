"""
Tests for resilience utilities.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from probablyprofit.api.exceptions import NetworkException, RateLimitException
from probablyprofit.utils.resilience import (
    CircuitBreaker,
    CircuitState,
    RateLimiter,
    RetryConfig,
    calculate_delay,
    get_resilience_status,
    reset_all_circuit_breakers,
    retry,
)


class TestRetry:
    """Tests for retry decorator."""

    @pytest.mark.asyncio
    async def test_retry_succeeds_first_try(self):
        """Function succeeds on first try, no retries needed."""
        call_count = 0

        @retry(max_attempts=3)
        async def succeed():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await succeed()
        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_succeeds_after_failures(self):
        """Function succeeds after initial failures."""
        call_count = 0

        @retry(max_attempts=3, base_delay=0.01)
        async def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise NetworkException("Network error")
            return "success"

        result = await fail_then_succeed()
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_exhausts_attempts(self):
        """All retries exhausted, raises last exception."""
        call_count = 0

        @retry(max_attempts=3, base_delay=0.01)
        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise NetworkException("Always fails")

        with pytest.raises(NetworkException):
            await always_fail()

        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_non_retryable_exception(self):
        """Non-retryable exceptions are raised immediately."""
        call_count = 0

        @retry(max_attempts=3)
        async def raise_value_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("Not retryable")

        with pytest.raises(ValueError):
            await raise_value_error()

        # Should only be called once
        assert call_count == 1


class TestCircuitBreaker:
    """Tests for circuit breaker."""

    @pytest.mark.asyncio
    async def test_circuit_starts_closed(self):
        """Circuit breaker starts in closed state."""
        breaker = CircuitBreaker("test-1", failure_threshold=3)
        assert breaker.state == CircuitState.CLOSED
        assert breaker.is_closed

    @pytest.mark.asyncio
    async def test_circuit_opens_after_threshold(self):
        """Circuit opens after reaching failure threshold."""
        breaker = CircuitBreaker("test-2", failure_threshold=2)

        @breaker
        async def failing_func():
            raise NetworkException("fail")

        # First failure
        with pytest.raises(NetworkException):
            await failing_func()
        assert breaker.state == CircuitState.CLOSED

        # Second failure - should open circuit
        with pytest.raises(NetworkException):
            await failing_func()
        assert breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_circuit_rejects_when_open(self):
        """Open circuit immediately rejects calls."""
        breaker = CircuitBreaker("test-3", failure_threshold=1)

        @breaker
        async def failing_func():
            raise NetworkException("fail")

        # Trigger circuit open
        with pytest.raises(NetworkException):
            await failing_func()

        assert breaker.is_open

        # Next call should be rejected immediately
        from probablyprofit.api.exceptions import APIException

        with pytest.raises(APIException) as exc_info:
            await failing_func()

        assert "OPEN" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_circuit_success_resets_failures(self):
        """Successful calls reset the failure counter."""
        breaker = CircuitBreaker("test-4", failure_threshold=3)
        call_count = 0

        @breaker
        async def sometimes_fail():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise NetworkException("first failure")
            return "success"

        # First call fails
        with pytest.raises(NetworkException):
            await sometimes_fail()

        # Second call succeeds
        result = await sometimes_fail()
        assert result == "success"
        assert breaker._failure_count == 0

    def test_circuit_reset(self):
        """Manual reset works."""
        breaker = CircuitBreaker("test-5", failure_threshold=1)
        breaker._state = CircuitState.OPEN
        breaker._failure_count = 5

        breaker.reset()

        assert breaker.state == CircuitState.CLOSED
        assert breaker._failure_count == 0


class TestRateLimiter:
    """Tests for rate limiter."""

    @pytest.mark.asyncio
    async def test_rate_limiter_allows_within_limit(self):
        """Calls within rate limit proceed immediately."""
        limiter = RateLimiter("test-rl-1", calls=5, period=1.0)

        @limiter
        async def quick_call():
            return "done"

        # Should be able to make 5 calls quickly
        for _ in range(5):
            result = await quick_call()
            assert result == "done"

    @pytest.mark.asyncio
    async def test_acquire_returns_wait_time(self):
        """Acquire returns wait time when tokens exhausted."""
        limiter = RateLimiter("test-rl-2", calls=2, period=1.0)

        # Exhaust tokens
        wait1 = await limiter.acquire()
        assert wait1 == 0.0

        wait2 = await limiter.acquire()
        assert wait2 == 0.0

        # Third acquire should have wait time
        wait3 = await limiter.acquire()
        assert wait3 > 0


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_calculate_delay_exponential(self):
        """Delay increases exponentially with attempts."""
        config = RetryConfig(base_delay=1.0, exponential_base=2.0, jitter=False)

        delay0 = calculate_delay(0, config)
        delay1 = calculate_delay(1, config)
        delay2 = calculate_delay(2, config)

        assert delay0 == 1.0
        assert delay1 == 2.0
        assert delay2 == 4.0

    def test_calculate_delay_respects_max(self):
        """Delay is capped at max_delay."""
        config = RetryConfig(base_delay=1.0, max_delay=5.0, exponential_base=2.0, jitter=False)

        delay10 = calculate_delay(10, config)
        assert delay10 == 5.0

    def test_get_resilience_status(self):
        """Get status returns circuit breaker states."""
        # Reset first
        reset_all_circuit_breakers()

        # Create some breakers
        CircuitBreaker("status-test-1")
        CircuitBreaker("status-test-2")

        status = get_resilience_status()
        assert "circuit_breakers" in status
        assert "status-test-1" in status["circuit_breakers"]
        assert "status-test-2" in status["circuit_breakers"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
