"""Utility functions."""


def __getattr__(name):
    """Lazy import handler to avoid circular imports."""
    # Logging
    if name == "setup_logging":
        from probablyprofit.utils.logging import setup_logging

        return setup_logging
    if name == "register_secret":
        from probablyprofit.utils.logging import register_secret

        return register_secret
    if name == "redact_string":
        from probablyprofit.utils.logging import redact_string

        return redact_string
    if name == "redact_dict":
        from probablyprofit.utils.logging import redact_dict

        return redact_dict
    if name == "get_safe_repr":
        from probablyprofit.utils.logging import get_safe_repr

        return get_safe_repr

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

    # Secrets Management
    if name == "SecretsManager":
        from probablyprofit.utils.secrets import SecretsManager

        return SecretsManager
    if name == "get_secrets_manager":
        from probablyprofit.utils.secrets import get_secrets_manager

        return get_secrets_manager
    if name == "get_secret":
        from probablyprofit.utils.secrets import get_secret

        return get_secret
    if name == "set_secret":
        from probablyprofit.utils.secrets import set_secret

        return set_secret
    if name == "redact_secret":
        from probablyprofit.utils.secrets import redact_secret

        return redact_secret

    raise AttributeError(f"module 'probablyprofit.utils' has no attribute '{name}'")


__all__ = [
    # Logging
    "setup_logging",
    "register_secret",
    "redact_string",
    "redact_dict",
    "get_safe_repr",
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
    # Secrets Management
    "SecretsManager",
    "get_secrets_manager",
    "get_secret",
    "set_secret",
    "redact_secret",
]
