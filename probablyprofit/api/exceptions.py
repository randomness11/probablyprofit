"""
Custom exceptions for probablyprofit API.
"""


class Poly16zException(Exception):
    """Base exception for all probablyprofit errors."""
    pass


class APIException(Poly16zException):
    """API-related errors."""
    pass


class NetworkException(APIException):
    """Network connectivity issues."""
    pass


class AuthenticationException(APIException):
    """Authentication/authorization failures."""
    pass


class RateLimitException(APIException):
    """Rate limit exceeded."""
    pass


class ValidationException(Poly16zException):
    """Input validation errors."""
    pass


class OrderException(Poly16zException):
    """Order placement/management errors."""
    pass


class InsufficientBalanceException(OrderException):
    """Insufficient balance for order."""
    pass


class RiskLimitException(Poly16zException):
    """Risk limit violations."""
    pass


class ConfigurationException(Poly16zException):
    """Configuration errors."""
    pass


class AgentException(Poly16zException):
    """Agent execution errors."""
    pass


class BacktestException(Poly16zException):
    """Backtesting errors."""
    pass
