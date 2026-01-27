"""
Logging utilities with secret redaction.

Provides secure logging that automatically redacts sensitive information
like API keys, private keys, and other secrets from log output.
"""

import re
import sys
from typing import Any, Dict, List, Optional, Pattern

from loguru import logger

# Patterns that look like secrets (compiled for performance)
SECRET_PATTERNS: List[Pattern] = [
    # API keys (common formats)
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),  # OpenAI
    re.compile(r"sk-ant-[a-zA-Z0-9\-]{20,}"),  # Anthropic
    re.compile(r"AIza[a-zA-Z0-9_\-]{35}"),  # Google
    re.compile(r"pplx-[a-zA-Z0-9]{20,}"),  # Perplexity (full pattern)
    re.compile(r"pplx-[a-zA-Z0-9]{8,}"),  # Perplexity (shorter keys)
    # Telegram bot tokens (format: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz)
    re.compile(r"\d{8,10}:[a-zA-Z0-9_-]{35}"),
    # Reddit credentials
    re.compile(r"[a-zA-Z0-9_-]{14}"),  # Reddit client ID (14 chars)
    re.compile(r"[a-zA-Z0-9_-]{27}"),  # Reddit client secret (27 chars)
    # Twitter/X Bearer tokens
    re.compile(r"AAAA[a-zA-Z0-9%]{40,}"),  # Twitter Bearer token format
    # Discord tokens
    re.compile(r"[MN][a-zA-Z0-9_-]{23,}\.[a-zA-Z0-9_-]{6}\.[a-zA-Z0-9_-]{27,}"),
    # Ethereum private keys (64 hex chars, with or without 0x)
    re.compile(r"0x[a-fA-F0-9]{64}"),
    re.compile(r"(?<![a-fA-F0-9])[a-fA-F0-9]{64}(?![a-fA-F0-9])"),
    # Bearer tokens in headers
    re.compile(r"Bearer\s+[a-zA-Z0-9\-_.~+/]+=*", re.IGNORECASE),
    # Basic auth patterns
    re.compile(r"Basic\s+[a-zA-Z0-9+/]+=*", re.IGNORECASE),
    # AWS-style keys
    re.compile(r"AKIA[A-Z0-9]{16}"),  # AWS Access Key ID
    re.compile(r"[a-zA-Z0-9/+]{40}"),  # AWS Secret Access Key (40 chars)
    # Generic long alphanumeric strings that look like keys (32+ chars)
    re.compile(r"(?<![a-zA-Z0-9])[a-zA-Z0-9]{32,}(?![a-zA-Z0-9])"),
]

# Keywords that indicate a value might be sensitive
SENSITIVE_KEYWORDS = [
    "api_key",
    "apikey",
    "api-key",
    "secret",
    "password",
    "passwd",
    "private_key",
    "privatekey",
    "private-key",
    "token",
    "bearer",
    "auth",
    "credential",
    "key",
    # Telegram specific
    "bot_token",
    "telegram_token",
    "chat_id",
    # Reddit specific
    "client_id",
    "client_secret",
    "reddit_password",
    "reddit_secret",
    # Social media
    "twitter_token",
    "twitter_bearer",
    "discord_token",
    # Perplexity
    "perplexity_key",
    "perplexity_api",
    # Database
    "db_password",
    "database_url",
    "connection_string",
    # Wallet
    "wallet_key",
    "mnemonic",
    "seed_phrase",
]

# Values to always redact (populated at runtime)
_known_secrets: set = set()


def register_secret(value: str) -> None:
    """
    Register a known secret value to always redact.

    Args:
        value: Secret value to redact in all logs
    """
    if value and len(value) > 4:
        _known_secrets.add(value)


def redact_string(text: str, show_chars: int = 4) -> str:
    """
    Redact sensitive patterns from a string.

    Args:
        text: String to redact
        show_chars: Number of characters to show at end

    Returns:
        Redacted string
    """
    if not text:
        return text

    result = text

    # Redact known secrets first (exact match)
    for secret in _known_secrets:
        if secret in result:
            redacted = "*" * (len(secret) - show_chars) + secret[-show_chars:]
            result = result.replace(secret, redacted)

    # Redact patterns that look like secrets
    for pattern in SECRET_PATTERNS:

        def replacer(match: re.Match[str]) -> str:
            value = match.group(0)
            if len(value) <= show_chars:
                return "*" * len(value)
            return "*" * (len(value) - show_chars) + value[-show_chars:]

        result = pattern.sub(replacer, result)

    return result


def redact_dict(data: Dict[str, Any], depth: int = 0, max_depth: int = 10) -> Dict[str, Any]:
    """
    Redact sensitive values from a dictionary.

    Args:
        data: Dictionary to redact
        depth: Current recursion depth
        max_depth: Maximum recursion depth

    Returns:
        Dictionary with sensitive values redacted
    """
    if depth > max_depth:
        return data

    result = {}
    for key, value in data.items():
        key_lower = key.lower()

        # Check if key indicates sensitive data
        is_sensitive_key = any(kw in key_lower for kw in SENSITIVE_KEYWORDS)

        if isinstance(value, str):
            if is_sensitive_key:
                # Key suggests this is sensitive - redact more aggressively
                result[key] = (
                    "*" * max(len(value) - 4, 0) + value[-4:] if len(value) > 4 else "****"
                )
            else:
                # Apply pattern-based redaction
                result[key] = redact_string(value)
        elif isinstance(value, dict):
            result[key] = redact_dict(value, depth + 1, max_depth)
        elif isinstance(value, list):
            result[key] = [
                (
                    redact_dict(item, depth + 1, max_depth)
                    if isinstance(item, dict)
                    else redact_string(item) if isinstance(item, str) else item
                )
                for item in value
            ]
        else:
            result[key] = value

    return result


class SecretFilter:
    """Loguru filter that redacts secrets from log messages."""

    def __call__(self, record: Dict[str, Any]) -> bool:
        """
        Filter log record, redacting any secrets.

        Args:
            record: Loguru log record

        Returns:
            True (always emit the record, but with redacted content)
        """
        # Redact the message
        if "message" in record:
            record["message"] = redact_string(record["message"])

        # Redact extra data if present
        if "extra" in record and record["extra"]:
            record["extra"] = redact_dict(record["extra"])

        return True


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    redact_secrets: bool = True,
) -> None:
    """
    Setup logging configuration with optional secret redaction.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional log file path
        redact_secrets: Whether to enable secret redaction (default: True)
    """
    # Remove default handler
    logger.remove()

    # Create filter
    log_filter = SecretFilter() if redact_secrets else None

    # Add console handler
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level=level,
        colorize=True,
        filter=log_filter,
    )

    # Add file handler if specified
    if log_file:
        logger.add(
            log_file,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function} - {message}",
            level=level,
            rotation="10 MB",
            retention="1 week",
            filter=log_filter,
        )

    if redact_secrets:
        logger.info("Logging initialized with secret redaction enabled")
    else:
        logger.info(f"Logging initialized at {level} level")


def get_safe_repr(obj: Any, max_length: int = 200) -> str:
    """
    Get a safe string representation of an object for logging.

    Automatically redacts secrets and truncates long strings.

    Args:
        obj: Object to represent
        max_length: Maximum length of output

    Returns:
        Safe string representation
    """
    if obj is None:
        return "None"

    if isinstance(obj, dict):
        safe_dict = redact_dict(obj)
        result = str(safe_dict)
    elif isinstance(obj, str):
        result = redact_string(obj)
    else:
        result = str(obj)
        result = redact_string(result)

    if len(result) > max_length:
        result = result[:max_length] + "..."

    return result
