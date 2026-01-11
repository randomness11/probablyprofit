"""
Tests for WebSocket Client.
"""
import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

# Check if websockets is available
try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not WEBSOCKETS_AVAILABLE,
    reason="websockets package not installed"
)


class TestPriceUpdate:
    """Tests for PriceUpdate dataclass."""

    def test_creation(self):
        from probablyprofit.api.websocket import PriceUpdate

        update = PriceUpdate(
            market_id="0x123",
            outcome="Yes",
            price=0.65,
            timestamp=datetime.now(),
            volume=1000.0,
        )
        assert update.market_id == "0x123"
        assert update.price == 0.65


class TestOrderbookUpdate:
    """Tests for OrderbookUpdate dataclass."""

    def test_creation(self):
        from probablyprofit.api.websocket import OrderbookUpdate

        update = OrderbookUpdate(
            market_id="0x123",
            outcome="Yes",
            bids=[(0.60, 100), (0.59, 200)],
            asks=[(0.62, 150), (0.63, 250)],
            timestamp=datetime.now(),
        )
        assert len(update.bids) == 2
        assert len(update.asks) == 2


class TestWebSocketClient:
    """Tests for WebSocketClient."""

    def test_initialization(self):
        from probablyprofit.api.websocket import WebSocketClient

        client = WebSocketClient()
        assert client.is_connected is False
        assert client.subscriptions == set()

    def test_callback_registration(self):
        from probablyprofit.api.websocket import WebSocketClient

        client = WebSocketClient()
        callback_called = [False]

        @client.on_price_update
        def handle_price(update):
            callback_called[0] = True

        assert len(client._price_callbacks) == 1

    def test_subscribe_before_connect(self):
        from probablyprofit.api.websocket import WebSocketClient

        client = WebSocketClient()
        # Subscribe adds to pending subscriptions even when not connected
        asyncio.get_event_loop().run_until_complete(
            client.subscribe(["0x123", "0x456"])
        )
        assert "0x123" in client._subscriptions
        assert "0x456" in client._subscriptions

    def test_stats(self):
        from probablyprofit.api.websocket import WebSocketClient

        client = WebSocketClient()
        stats = client.stats

        assert "connected" in stats
        assert "subscriptions" in stats
        assert "messages_received" in stats
        assert stats["connected"] is False

    def test_parse_price_update(self):
        from probablyprofit.api.websocket import WebSocketClient

        client = WebSocketClient()

        data = {
            "market": "0x123",
            "outcome": "Yes",
            "price": "0.65",
            "volume": "1000",
        }

        update = client._parse_price_update(data)
        assert update is not None
        assert update.market_id == "0x123"
        assert update.price == 0.65

    def test_parse_orderbook_update(self):
        from probablyprofit.api.websocket import WebSocketClient

        client = WebSocketClient()

        data = {
            "market": "0x123",
            "outcome": "Yes",
            "bids": [{"price": "0.60", "size": "100"}],
            "asks": [{"price": "0.62", "size": "150"}],
        }

        update = client._parse_orderbook_update(data)
        assert update is not None
        assert update.market_id == "0x123"
        assert len(update.bids) == 1
        assert len(update.asks) == 1


class TestWebSocketCallbacks:
    """Tests for callback handling."""

    def test_on_connect_callback(self):
        from probablyprofit.api.websocket import WebSocketClient

        client = WebSocketClient()
        connect_called = [False]

        @client.on_connect
        def handle_connect():
            connect_called[0] = True

        assert len(client._connect_callbacks) == 1

    def test_on_disconnect_callback(self):
        from probablyprofit.api.websocket import WebSocketClient

        client = WebSocketClient()
        disconnect_called = [False]

        @client.on_disconnect
        def handle_disconnect():
            disconnect_called[0] = True

        assert len(client._disconnect_callbacks) == 1

    def test_on_error_callback(self):
        from probablyprofit.api.websocket import WebSocketClient

        client = WebSocketClient()
        error_received = [None]

        @client.on_error
        def handle_error(e):
            error_received[0] = e

        assert len(client._error_callbacks) == 1


class TestWebSocketMocked:
    """Tests with mocked WebSocket connection."""

    @pytest.mark.asyncio
    async def test_handle_message_price(self):
        from probablyprofit.api.websocket import WebSocketClient

        client = WebSocketClient()
        received_updates = []

        @client.on_price_update
        async def handle_price(update):
            received_updates.append(update)

        # Simulate receiving a message
        message = '{"type": "price", "market": "0x123", "outcome": "Yes", "price": "0.65"}'
        await client._handle_message(message)

        assert len(received_updates) == 1
        assert received_updates[0].market_id == "0x123"

    @pytest.mark.asyncio
    async def test_handle_message_invalid_json(self):
        from probablyprofit.api.websocket import WebSocketClient

        client = WebSocketClient()

        # Should not raise, just log warning
        await client._handle_message("not valid json")
