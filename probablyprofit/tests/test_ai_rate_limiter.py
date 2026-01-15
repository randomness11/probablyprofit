"""
Tests for AI Provider Rate Limiting.
"""

import asyncio
import time

import pytest

from probablyprofit.utils.ai_rate_limiter import (
    AI_PROVIDER_LIMITS,
    AIRateLimiter,
    ai_resilient,
    anthropic_rate_limited,
    get_all_ai_limiter_stats,
    openai_rate_limited,
)


class TestAIProviderLimits:
    """Tests for AI provider limit configurations."""

    def test_known_providers(self):
        assert "openai" in AI_PROVIDER_LIMITS
        assert "anthropic" in AI_PROVIDER_LIMITS
        assert "gemini" in AI_PROVIDER_LIMITS

    def test_provider_limits_structure(self):
        for provider, limits in AI_PROVIDER_LIMITS.items():
            assert limits.requests_per_minute > 0
            assert limits.tokens_per_minute > 0


class TestAIRateLimiter:
    """Tests for AIRateLimiter."""

    def test_initialization(self):
        limiter = AIRateLimiter("test_provider")
        assert limiter.provider == "test_provider"
        assert limiter.requests_per_minute > 0

    def test_get_or_create(self):
        # First call creates
        limiter1 = AIRateLimiter.get_or_create("test_singleton")

        # Second call returns same instance
        limiter2 = AIRateLimiter.get_or_create("test_singleton")

        assert limiter1 is limiter2

    def test_get_nonexistent(self):
        result = AIRateLimiter.get("definitely_not_exists_12345")
        assert result is None

    @pytest.mark.asyncio
    async def test_acquire_basic(self):
        limiter = AIRateLimiter(
            "test_acquire",
            requests_per_minute=60,
            tokens_per_minute=10000,
        )

        # Should not wait for first request
        wait_time = await limiter.acquire(estimated_tokens=100)
        assert wait_time >= 0

    @pytest.mark.asyncio
    async def test_acquire_tracks_tokens(self):
        limiter = AIRateLimiter(
            "test_tokens",
            requests_per_minute=60,
            tokens_per_minute=1000,
        )

        await limiter.acquire(estimated_tokens=500)
        assert limiter._tokens_used == 500

        await limiter.acquire(estimated_tokens=300)
        assert limiter._tokens_used == 800

    def test_record_success(self):
        limiter = AIRateLimiter("test_success")
        limiter._consecutive_429s = 5
        limiter.record_success()
        assert limiter._consecutive_429s == 0

    def test_record_rate_limit_error(self):
        limiter = AIRateLimiter("test_429")
        limiter.record_rate_limit_error()

        assert limiter._rate_limit_hits == 1
        assert limiter._consecutive_429s == 1
        assert limiter._backoff_until is not None

    def test_record_rate_limit_with_retry_after(self):
        limiter = AIRateLimiter("test_retry_after")
        limiter.record_rate_limit_error(retry_after=30.0)

        expected_backoff = time.time() + 30.0
        assert limiter._backoff_until == pytest.approx(expected_backoff, abs=1.0)

    def test_stats(self):
        limiter = AIRateLimiter("test_stats_limiter")
        limiter._total_requests = 100
        limiter._total_tokens = 50000
        limiter._rate_limit_hits = 2

        stats = limiter.stats
        assert stats["provider"] == "test_stats_limiter"
        assert stats["total_requests"] == 100
        assert stats["total_tokens"] == 50000
        assert stats["rate_limit_hits"] == 2

    @pytest.mark.asyncio
    async def test_limit_decorator(self):
        limiter = AIRateLimiter("test_decorator", requests_per_minute=60)

        call_count = [0]

        @limiter.limit(estimated_tokens=100)
        async def my_function():
            call_count[0] += 1
            return "success"

        result = await my_function()
        assert result == "success"
        assert call_count[0] == 1
        assert limiter._total_requests == 1

    @pytest.mark.asyncio
    async def test_limit_decorator_records_success(self):
        limiter = AIRateLimiter("test_decorator_success")
        limiter._consecutive_429s = 3

        @limiter.limit()
        async def successful_call():
            return "ok"

        await successful_call()
        assert limiter._consecutive_429s == 0


class TestConvenienceDecorators:
    """Tests for convenience decorators."""

    @pytest.mark.asyncio
    async def test_openai_rate_limited(self):
        @openai_rate_limited(estimated_tokens=500)
        async def call_openai():
            return "response"

        result = await call_openai()
        assert result == "response"

        limiter = AIRateLimiter.get("openai")
        assert limiter is not None

    @pytest.mark.asyncio
    async def test_anthropic_rate_limited(self):
        @anthropic_rate_limited(estimated_tokens=1000)
        async def call_anthropic():
            return "claude response"

        result = await call_anthropic()
        assert result == "claude response"

        limiter = AIRateLimiter.get("anthropic")
        assert limiter is not None


class TestGetAllStats:
    """Tests for stats aggregation."""

    def test_get_all_stats(self):
        # Create some limiters
        AIRateLimiter.get_or_create("stats_test_1")
        AIRateLimiter.get_or_create("stats_test_2")

        stats = get_all_ai_limiter_stats()
        assert "stats_test_1" in stats
        assert "stats_test_2" in stats
