"""
AI Provider Rate Limiting

Rate limiters specifically configured for AI API providers
(OpenAI, Anthropic, Google) with their known rate limits.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Dict, Optional, Callable, Any, TypeVar
from functools import wraps
from loguru import logger

from probablyprofit.utils.resilience import RateLimiter, retry


T = TypeVar("T")


@dataclass
class AIProviderLimits:
    """Rate limit configuration for an AI provider."""
    requests_per_minute: int
    tokens_per_minute: int
    requests_per_day: Optional[int] = None


# Known rate limits for AI providers (as of 2024)
# These are conservative defaults - actual limits vary by tier
AI_PROVIDER_LIMITS = {
    "openai": AIProviderLimits(
        requests_per_minute=60,  # GPT-4 tier 1
        tokens_per_minute=10000,
        requests_per_day=10000,
    ),
    "anthropic": AIProviderLimits(
        requests_per_minute=50,  # Claude tier 1
        tokens_per_minute=40000,
        requests_per_day=None,
    ),
    "gemini": AIProviderLimits(
        requests_per_minute=60,
        tokens_per_minute=60000,
        requests_per_day=1500,
    ),
}


class AIRateLimiter:
    """
    Rate limiter specifically for AI API providers.

    Features:
    - Per-minute request limiting
    - Token budget tracking
    - Automatic backoff on 429 errors
    - Provider-specific defaults

    Usage:
        limiter = AIRateLimiter("anthropic")

        @limiter.limit
        async def call_claude():
            ...
    """

    # Class-level registry of all AI rate limiters
    _limiters: Dict[str, "AIRateLimiter"] = {}

    def __init__(
        self,
        provider: str,
        requests_per_minute: Optional[int] = None,
        tokens_per_minute: Optional[int] = None,
    ):
        """
        Initialize AI rate limiter.

        Args:
            provider: AI provider name (openai, anthropic, gemini)
            requests_per_minute: Override default RPM limit
            tokens_per_minute: Override default TPM limit
        """
        self.provider = provider

        # Get default limits
        defaults = AI_PROVIDER_LIMITS.get(
            provider.lower(),
            AIProviderLimits(requests_per_minute=30, tokens_per_minute=10000)
        )

        self.requests_per_minute = requests_per_minute or defaults.requests_per_minute
        self.tokens_per_minute = tokens_per_minute or defaults.tokens_per_minute

        # Request rate limiter
        self._request_limiter = RateLimiter(
            f"{provider}-requests",
            calls=self.requests_per_minute,
            period=60.0,
            burst=5,  # Allow small bursts
        )

        # Token tracking
        self._tokens_used = 0
        self._token_window_start = time.time()
        self._token_lock = asyncio.Lock()

        # Backoff state
        self._backoff_until: Optional[float] = None
        self._consecutive_429s = 0

        # Statistics
        self._total_requests = 0
        self._total_tokens = 0
        self._rate_limit_hits = 0

        # Register
        AIRateLimiter._limiters[provider] = self

        logger.info(
            f"[AIRateLimiter] '{provider}' initialized "
            f"(RPM: {self.requests_per_minute}, TPM: {self.tokens_per_minute})"
        )

    async def acquire(self, estimated_tokens: int = 1000) -> float:
        """
        Acquire permission to make a request.

        Args:
            estimated_tokens: Estimated tokens for this request

        Returns:
            Wait time in seconds (0 if no wait needed)
        """
        total_wait = 0.0

        # Check if in backoff period
        if self._backoff_until and time.time() < self._backoff_until:
            wait_time = self._backoff_until - time.time()
            logger.warning(f"[AIRateLimiter] '{self.provider}' in backoff, waiting {wait_time:.1f}s")
            await asyncio.sleep(wait_time)
            total_wait += wait_time

        # Request rate limiting
        request_wait = await self._request_limiter.acquire()
        if request_wait > 0:
            await asyncio.sleep(request_wait)
            total_wait += request_wait

        # Token rate limiting
        async with self._token_lock:
            now = time.time()

            # Reset window if expired
            if now - self._token_window_start >= 60.0:
                self._tokens_used = 0
                self._token_window_start = now

            # Check if we'd exceed token limit
            if self._tokens_used + estimated_tokens > self.tokens_per_minute:
                # Wait until window resets
                wait_time = 60.0 - (now - self._token_window_start)
                if wait_time > 0:
                    logger.warning(
                        f"[AIRateLimiter] '{self.provider}' token limit reached, "
                        f"waiting {wait_time:.1f}s"
                    )
                    await asyncio.sleep(wait_time)
                    total_wait += wait_time

                    # Reset after waiting
                    self._tokens_used = 0
                    self._token_window_start = time.time()

            self._tokens_used += estimated_tokens

        self._total_requests += 1
        return total_wait

    def record_tokens(self, actual_tokens: int) -> None:
        """
        Record actual token usage (call after request completes).

        Args:
            actual_tokens: Actual tokens used
        """
        self._total_tokens += actual_tokens

    def record_rate_limit_error(self, retry_after: Optional[float] = None) -> None:
        """
        Record a rate limit error (429 response).

        Args:
            retry_after: Retry-After header value if provided
        """
        self._rate_limit_hits += 1
        self._consecutive_429s += 1

        # Calculate backoff
        if retry_after:
            backoff = retry_after
        else:
            # Exponential backoff: 5s, 10s, 20s, 40s, max 60s
            backoff = min(5.0 * (2 ** self._consecutive_429s), 60.0)

        self._backoff_until = time.time() + backoff

        logger.warning(
            f"[AIRateLimiter] '{self.provider}' rate limited "
            f"(consecutive: {self._consecutive_429s}, backoff: {backoff:.1f}s)"
        )

    def record_success(self) -> None:
        """Record a successful request (resets consecutive 429 counter)."""
        self._consecutive_429s = 0

    @property
    def stats(self) -> Dict[str, Any]:
        """Get rate limiter statistics."""
        return {
            "provider": self.provider,
            "requests_per_minute": self.requests_per_minute,
            "tokens_per_minute": self.tokens_per_minute,
            "total_requests": self._total_requests,
            "total_tokens": self._total_tokens,
            "rate_limit_hits": self._rate_limit_hits,
            "tokens_used_current_window": self._tokens_used,
            "in_backoff": self._backoff_until is not None and time.time() < self._backoff_until,
        }

    def limit(self, estimated_tokens: int = 1000):
        """
        Decorator to rate limit a function.

        Args:
            estimated_tokens: Estimated tokens per call

        Usage:
            @limiter.limit(estimated_tokens=2000)
            async def call_api():
                ...
        """
        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            @wraps(func)
            async def wrapper(*args, **kwargs) -> T:
                await self.acquire(estimated_tokens)

                try:
                    result = await func(*args, **kwargs)
                    self.record_success()
                    return result

                except Exception as e:
                    # Check for rate limit errors
                    error_str = str(e).lower()
                    if "429" in error_str or "rate" in error_str and "limit" in error_str:
                        # Try to extract retry-after
                        retry_after = None
                        if hasattr(e, "response") and hasattr(e.response, "headers"):
                            retry_after = e.response.headers.get("retry-after")
                            if retry_after:
                                retry_after = float(retry_after)

                        self.record_rate_limit_error(retry_after)
                    raise

            return wrapper
        return decorator

    @classmethod
    def get(cls, provider: str) -> Optional["AIRateLimiter"]:
        """Get rate limiter by provider name."""
        return cls._limiters.get(provider)

    @classmethod
    def get_or_create(cls, provider: str) -> "AIRateLimiter":
        """Get or create rate limiter for provider."""
        if provider not in cls._limiters:
            cls(provider)
        return cls._limiters[provider]


# =============================================================================
# CONVENIENCE DECORATORS
# =============================================================================

def openai_rate_limited(estimated_tokens: int = 1000):
    """Decorator for OpenAI API calls."""
    limiter = AIRateLimiter.get_or_create("openai")
    return limiter.limit(estimated_tokens)


def anthropic_rate_limited(estimated_tokens: int = 1000):
    """Decorator for Anthropic API calls."""
    limiter = AIRateLimiter.get_or_create("anthropic")
    return limiter.limit(estimated_tokens)


def gemini_rate_limited(estimated_tokens: int = 1000):
    """Decorator for Google Gemini API calls."""
    limiter = AIRateLimiter.get_or_create("gemini")
    return limiter.limit(estimated_tokens)


def ai_rate_limited(provider: str, estimated_tokens: int = 1000):
    """
    Generic decorator for any AI provider.

    Usage:
        @ai_rate_limited("anthropic", estimated_tokens=2000)
        async def call_claude():
            ...
    """
    limiter = AIRateLimiter.get_or_create(provider)
    return limiter.limit(estimated_tokens)


# =============================================================================
# COMBINED RETRY + RATE LIMIT
# =============================================================================

def ai_resilient(
    provider: str,
    estimated_tokens: int = 1000,
    max_retries: int = 3,
    base_delay: float = 1.0,
):
    """
    Combined retry and rate limiting for AI calls.

    Applies rate limiting and retries with exponential backoff
    for transient errors.

    Usage:
        @ai_resilient("anthropic", estimated_tokens=2000, max_retries=3)
        async def call_claude():
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        # Apply rate limiting first
        rate_limited_func = ai_rate_limited(provider, estimated_tokens)(func)

        # Then apply retry
        @retry(max_attempts=max_retries, base_delay=base_delay)
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await rate_limited_func(*args, **kwargs)

        return wrapper
    return decorator


def get_all_ai_limiter_stats() -> Dict[str, Dict[str, Any]]:
    """Get statistics for all AI rate limiters."""
    return {
        name: limiter.stats
        for name, limiter in AIRateLimiter._limiters.items()
    }
