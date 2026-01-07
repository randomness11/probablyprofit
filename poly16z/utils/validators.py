"""
Input validation utilities.
"""

from typing import Optional
from poly16z.api.exceptions import ValidationException


def validate_price(price: float, field_name: str = "price") -> None:
    """
    Validate price is between 0 and 1.

    Args:
        price: Price to validate
        field_name: Name of field for error message

    Raises:
        ValidationException: If price is invalid
    """
    if not isinstance(price, (int, float)):
        raise ValidationException(f"{field_name} must be a number, got {type(price)}")

    if price < 0 or price > 1:
        raise ValidationException(f"{field_name} must be between 0 and 1, got {price}")


def validate_positive(value: float, field_name: str = "value") -> None:
    """
    Validate value is positive.

    Args:
        value: Value to validate
        field_name: Name of field for error message

    Raises:
        ValidationException: If value is invalid
    """
    if not isinstance(value, (int, float)):
        raise ValidationException(f"{field_name} must be a number, got {type(value)}")

    if value <= 0:
        raise ValidationException(f"{field_name} must be positive, got {value}")


def validate_non_negative(value: float, field_name: str = "value") -> None:
    """
    Validate value is non-negative.

    Args:
        value: Value to validate
        field_name: Name of field for error message

    Raises:
        ValidationException: If value is invalid
    """
    if not isinstance(value, (int, float)):
        raise ValidationException(f"{field_name} must be a number, got {type(value)}")

    if value < 0:
        raise ValidationException(f"{field_name} must be non-negative, got {value}")


def validate_confidence(confidence: float) -> None:
    """
    Validate confidence is between 0 and 1.

    Args:
        confidence: Confidence value to validate

    Raises:
        ValidationException: If confidence is invalid
    """
    validate_price(confidence, "confidence")


def validate_side(side: str) -> None:
    """
    Validate order side.

    Args:
        side: Order side (BUY or SELL)

    Raises:
        ValidationException: If side is invalid
    """
    if side not in ("BUY", "SELL"):
        raise ValidationException(f"side must be 'BUY' or 'SELL', got '{side}'")


def validate_private_key(key: str) -> None:
    """
    Validate Ethereum private key format.

    Args:
        key: Private key to validate

    Raises:
        ValidationException: If key is invalid
    """
    if not isinstance(key, str):
        raise ValidationException("Private key must be a string")

    # Remove 0x prefix if present
    key_clean = key[2:] if key.startswith("0x") else key

    if len(key_clean) != 64:
        raise ValidationException(
            f"Private key must be 64 hex characters (got {len(key_clean)})"
        )

    try:
        int(key_clean, 16)
    except ValueError:
        raise ValidationException("Private key must be valid hexadecimal")


def validate_address(address: str) -> None:
    """
    Validate Ethereum address format.

    Args:
        address: Ethereum address to validate

    Raises:
        ValidationException: If address is invalid
    """
    if not isinstance(address, str):
        raise ValidationException("Address must be a string")

    if not address.startswith("0x"):
        raise ValidationException("Address must start with '0x'")

    if len(address) != 42:
        raise ValidationException(f"Address must be 42 characters (got {len(address)})")

    try:
        int(address[2:], 16)
    except ValueError:
        raise ValidationException("Address must be valid hexadecimal")
