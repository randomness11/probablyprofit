"""Utility functions."""


def __getattr__(name):
    """Lazy import handler to avoid circular imports."""
    # Logging
    if name == "setup_logging":
        from probablyprofit.utils.logging import setup_logging
        return setup_logging

    # Resilience
    if name == "retry":
        from probablyprofit.utils.resilience import retry
        return retry
    if name == "resilient":
        from probablyprofit.utils.resilience import resilient
        return resilient
    if name == "with_timeout":
        from probablyprofit.utils.resilience import with_timeout
        return with_timeout
    if name == "CircuitBreaker":
        from probablyprofit.utils.resilience import CircuitBreaker
        return CircuitBreaker
    if name == "RateLimiter":
        from probablyprofit.utils.resilience import RateLimiter
        return RateLimiter
    if name == "RetryConfig":
        from probablyprofit.utils.resilience import RetryConfig
        return RetryConfig
    if name == "get_resilience_status":
        from probablyprofit.utils.resilience import get_resilience_status
        return get_resilience_status
    if name == "reset_all_circuit_breakers":
        from probablyprofit.utils.resilience import reset_all_circuit_breakers
        return reset_all_circuit_breakers

    # Recovery
    if name == "RecoveryManager":
        from probablyprofit.utils.recovery import RecoveryManager
        return RecoveryManager
    if name == "GracefulShutdown":
        from probablyprofit.utils.recovery import GracefulShutdown
        return GracefulShutdown
    if name == "AgentCheckpoint":
        from probablyprofit.utils.recovery import AgentCheckpoint
        return AgentCheckpoint
    if name == "get_recovery_manager":
        from probablyprofit.utils.recovery import get_recovery_manager
        return get_recovery_manager
    if name == "set_recovery_manager":
        from probablyprofit.utils.recovery import set_recovery_manager
        return set_recovery_manager

    # Cache
    if name == "TTLCache":
        from probablyprofit.utils.cache import TTLCache
        return TTLCache
    if name == "AsyncTTLCache":
        from probablyprofit.utils.cache import AsyncTTLCache
        return AsyncTTLCache

    # AI Rate Limiter
    if name == "AIRateLimiter":
        from probablyprofit.utils.ai_rate_limiter import AIRateLimiter
        return AIRateLimiter

    raise AttributeError(f"module 'probablyprofit.utils' has no attribute '{name}'")


__all__ = [
    "setup_logging",
    # Resilience
    "retry",
    "resilient",
    "with_timeout",
    "CircuitBreaker",
    "RateLimiter",
    "RetryConfig",
    "get_resilience_status",
    "reset_all_circuit_breakers",
    # Recovery
    "RecoveryManager",
    "GracefulShutdown",
    "AgentCheckpoint",
    "get_recovery_manager",
    "set_recovery_manager",
    # Cache
    "TTLCache",
    "AsyncTTLCache",
    # AI Rate Limiter
    "AIRateLimiter",
]
