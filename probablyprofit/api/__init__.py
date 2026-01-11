"""Polymarket API integration."""


def __getattr__(name):
    """Lazy import handler to avoid circular imports."""
    if name == "PolymarketClient":
        from probablyprofit.api.client import PolymarketClient
        return PolymarketClient
    elif name == "Market":
        from probablyprofit.api.client import Market
        return Market
    elif name == "Order":
        from probablyprofit.api.client import Order
        return Order
    elif name == "Position":
        from probablyprofit.api.client import Position
        return Position
    elif name == "KalshiClient":
        from probablyprofit.api.kalshi_client import KalshiClient
        return KalshiClient
    elif name == "WebSocketClient":
        from probablyprofit.api.websocket import WebSocketClient
        return WebSocketClient
    raise AttributeError(f"module 'probablyprofit.api' has no attribute '{name}'")


__all__ = [
    "PolymarketClient",
    "Market",
    "Order",
    "Position",
    "KalshiClient",
    "WebSocketClient",
]
