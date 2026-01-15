"""
WebSocket Client for Real-time Price Streaming

Provides real-time price updates from Polymarket via WebSocket.
Features automatic reconnection with exponential backoff and jitter.
"""

import asyncio
import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from loguru import logger


class ConnectionState(Enum):
    """WebSocket connection states."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"


try:
    import websockets
    from websockets.client import WebSocketClientProtocol

    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    logger.warning("websockets package not installed. Real-time streaming disabled.")


@dataclass
class PriceUpdate:
    """Represents a real-time price update."""

    market_id: str
    outcome: str
    price: float
    timestamp: datetime
    volume: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OrderbookUpdate:
    """Represents an orderbook update."""

    market_id: str
    outcome: str
    bids: List[tuple]  # [(price, size), ...]
    asks: List[tuple]
    timestamp: datetime


class WebSocketClient:
    """
    WebSocket client for Polymarket real-time data.

    Features:
    - Automatic reconnection
    - Subscription management
    - Price and orderbook streaming
    - Callback-based event handling

    Usage:
        ws = WebSocketClient()

        @ws.on_price_update
        async def handle_price(update: PriceUpdate):
            print(f"New price: {update.market_id} = {update.price}")

        await ws.connect()
        await ws.subscribe(["0x123", "0x456"])
    """

    # Polymarket WebSocket endpoint
    WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

    def __init__(
        self,
        url: Optional[str] = None,
        reconnect: bool = True,
        reconnect_interval: float = 5.0,
        max_reconnect_attempts: int = 10,
    ):
        """
        Initialize WebSocket client.

        Args:
            url: WebSocket URL (uses default if None)
            reconnect: Auto-reconnect on disconnect
            reconnect_interval: Seconds between reconnect attempts
            max_reconnect_attempts: Max reconnection attempts
        """
        if not WEBSOCKETS_AVAILABLE:
            raise ImportError("websockets package required. Install with: pip install websockets")

        self.url = url or self.WS_URL
        self.reconnect = reconnect
        self.reconnect_interval = reconnect_interval
        self.max_reconnect_attempts = max_reconnect_attempts

        self._ws: Optional[WebSocketClientProtocol] = None
        self._subscriptions: Set[str] = set()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._reconnect_count = 0
        self._state = ConnectionState.DISCONNECTED

        # Callbacks
        self._price_callbacks: List[Callable[[PriceUpdate], Any]] = []
        self._orderbook_callbacks: List[Callable[[OrderbookUpdate], Any]] = []
        self._error_callbacks: List[Callable[[Exception], Any]] = []
        self._connect_callbacks: List[Callable[[], Any]] = []
        self._disconnect_callbacks: List[Callable[[], Any]] = []

        # Statistics
        self._messages_received = 0
        self._last_message_time: Optional[datetime] = None
        self._connected_at: Optional[datetime] = None
        self._total_reconnects = 0

        # Heartbeat settings
        self._heartbeat_interval = 30.0  # seconds
        self._heartbeat_timeout = 60.0  # consider dead if no message for this long

        logger.info(f"WebSocketClient initialized (URL: {self.url})")

    async def connect(self) -> bool:
        """
        Connect to WebSocket server.

        Returns:
            True if connected successfully
        """
        self._state = ConnectionState.CONNECTING
        try:
            self._ws = await websockets.connect(
                self.url,
                ping_interval=30,
                ping_timeout=10,
            )
            self._running = True
            self._reconnect_count = 0
            self._state = ConnectionState.CONNECTED
            self._connected_at = datetime.now()

            logger.info("[WebSocket] Connected")

            # Fire connect callbacks
            for callback in self._connect_callbacks:
                try:
                    result = callback()
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.error(f"[WebSocket] Connect callback error: {e}")

            # Re-subscribe to previous subscriptions
            if self._subscriptions:
                await self._send_subscriptions(self._subscriptions)

            # Start message loop and heartbeat monitor
            self._task = asyncio.create_task(self._message_loop())
            self._heartbeat_task = asyncio.create_task(self._heartbeat_monitor())

            return True

        except Exception as e:
            logger.error(f"[WebSocket] Connection failed: {e}")
            self._state = ConnectionState.DISCONNECTED
            return False

    async def disconnect(self) -> None:
        """Disconnect from WebSocket server."""
        self._running = False
        self._state = ConnectionState.DISCONNECTED

        # Cancel heartbeat task
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self._ws:
            await self._ws.close()
            self._ws = None

        # Fire disconnect callbacks
        for callback in self._disconnect_callbacks:
            try:
                result = callback()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"[WebSocket] Disconnect callback error: {e}")

        logger.info("[WebSocket] Disconnected")

    async def subscribe(self, market_ids: List[str]) -> bool:
        """
        Subscribe to market updates.

        Args:
            market_ids: List of market condition IDs

        Returns:
            True if successful
        """
        new_subs = set(market_ids) - self._subscriptions
        if not new_subs:
            return True

        self._subscriptions.update(new_subs)

        if self._ws and self._running:
            return await self._send_subscriptions(new_subs)

        return True

    async def unsubscribe(self, market_ids: List[str]) -> bool:
        """
        Unsubscribe from market updates.

        Args:
            market_ids: List of market condition IDs

        Returns:
            True if successful
        """
        to_remove = set(market_ids) & self._subscriptions
        if not to_remove:
            return True

        self._subscriptions -= to_remove

        if self._ws and self._running:
            return await self._send_unsubscriptions(to_remove)

        return True

    async def _send_subscriptions(self, market_ids: Set[str]) -> bool:
        """Send subscription messages."""
        if not self._ws:
            return False

        try:
            for market_id in market_ids:
                msg = json.dumps(
                    {
                        "type": "subscribe",
                        "channel": "market",
                        "market": market_id,
                    }
                )
                await self._ws.send(msg)
                logger.debug(f"[WebSocket] Subscribed to {market_id}")

            return True

        except Exception as e:
            logger.error(f"[WebSocket] Subscription error: {e}")
            return False

    async def _send_unsubscriptions(self, market_ids: Set[str]) -> bool:
        """Send unsubscription messages."""
        if not self._ws:
            return False

        try:
            for market_id in market_ids:
                msg = json.dumps(
                    {
                        "type": "unsubscribe",
                        "channel": "market",
                        "market": market_id,
                    }
                )
                await self._ws.send(msg)

            return True

        except Exception as e:
            logger.error(f"[WebSocket] Unsubscription error: {e}")
            return False

    async def _message_loop(self) -> None:
        """Main message receiving loop."""
        while self._running and self._ws:
            try:
                message = await self._ws.recv()
                self._messages_received += 1
                self._last_message_time = datetime.now()

                await self._handle_message(message)

            except websockets.ConnectionClosed:
                logger.warning("[WebSocket] Connection closed")
                await self._handle_disconnect()
                break

            except Exception as e:
                logger.error(f"[WebSocket] Message loop error: {e}")
                await self._handle_error(e)

    async def _handle_message(self, message: str) -> None:
        """Handle incoming WebSocket message."""
        try:
            data = json.loads(message)

            msg_type = data.get("type", data.get("event", ""))

            if msg_type in ("price_change", "price", "tick"):
                update = self._parse_price_update(data)
                if update:
                    for callback in self._price_callbacks:
                        try:
                            result = callback(update)
                            if asyncio.iscoroutine(result):
                                await result
                        except Exception as e:
                            logger.error(f"[WebSocket] Price callback error: {e}")

            elif msg_type in ("orderbook", "book"):
                update = self._parse_orderbook_update(data)
                if update:
                    for callback in self._orderbook_callbacks:
                        try:
                            result = callback(update)
                            if asyncio.iscoroutine(result):
                                await result
                        except Exception as e:
                            logger.error(f"[WebSocket] Orderbook callback error: {e}")

        except json.JSONDecodeError:
            logger.warning(f"[WebSocket] Invalid JSON: {message[:100]}")

    def _parse_price_update(self, data: dict) -> Optional[PriceUpdate]:
        """Parse a price update from message data."""
        try:
            return PriceUpdate(
                market_id=data.get("market", data.get("condition_id", "")),
                outcome=data.get("outcome", data.get("asset", "Yes")),
                price=float(data.get("price", data.get("last_price", 0))),
                timestamp=datetime.now(),
                volume=float(data.get("volume", 0)),
                metadata=data,
            )
        except Exception as e:
            logger.debug(f"[WebSocket] Failed to parse price update: {e}")
            return None

    def _parse_orderbook_update(self, data: dict) -> Optional[OrderbookUpdate]:
        """Parse an orderbook update from message data."""
        try:
            return OrderbookUpdate(
                market_id=data.get("market", data.get("condition_id", "")),
                outcome=data.get("outcome", "Yes"),
                bids=[(float(b["price"]), float(b["size"])) for b in data.get("bids", [])],
                asks=[(float(a["price"]), float(a["size"])) for a in data.get("asks", [])],
                timestamp=datetime.now(),
            )
        except Exception as e:
            logger.debug(f"[WebSocket] Failed to parse orderbook update: {e}")
            return None

    async def _handle_disconnect(self) -> None:
        """Handle disconnection with optional reconnection."""
        self._ws = None

        # Fire disconnect callbacks
        for callback in self._disconnect_callbacks:
            try:
                result = callback()
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass

        if self.reconnect and self._running:
            await self._attempt_reconnect()

    async def _attempt_reconnect(self) -> None:
        """Attempt to reconnect with exponential backoff and jitter."""
        self._state = ConnectionState.RECONNECTING

        while self._running and self._reconnect_count < self.max_reconnect_attempts:
            self._reconnect_count += 1
            self._total_reconnects += 1

            # Exponential backoff with jitter to prevent thundering herd
            base_wait = self.reconnect_interval * (2 ** (self._reconnect_count - 1))
            base_wait = min(base_wait, 60.0)  # Cap at 60 seconds

            # Add jitter: random value between 0 and 25% of base_wait
            jitter = random.uniform(0, base_wait * 0.25)
            wait_time = base_wait + jitter

            logger.info(
                f"[WebSocket] Reconnecting in {wait_time:.1f}s "
                f"(attempt {self._reconnect_count}/{self.max_reconnect_attempts})"
            )

            await asyncio.sleep(wait_time)

            if await self.connect():
                logger.info(
                    f"[WebSocket] Reconnected successfully after {self._reconnect_count} attempt(s)"
                )
                return

        logger.error("[WebSocket] Max reconnection attempts reached")
        self._running = False
        self._state = ConnectionState.FAILED

    async def _heartbeat_monitor(self) -> None:
        """Monitor connection health and trigger reconnection if needed."""
        while self._running and self._state == ConnectionState.CONNECTED:
            await asyncio.sleep(self._heartbeat_interval)

            # Check if we've received any messages recently
            if self._last_message_time:
                time_since_last = (datetime.now() - self._last_message_time).total_seconds()
                if time_since_last > self._heartbeat_timeout:
                    logger.warning(
                        f"[WebSocket] No messages received for {time_since_last:.0f}s, "
                        "connection may be dead"
                    )
                    # Force disconnect and reconnect
                    if self._ws:
                        await self._ws.close()
                    await self._handle_disconnect()
                    break

    async def _handle_error(self, error: Exception) -> None:
        """Handle errors by calling error callbacks."""
        for callback in self._error_callbacks:
            try:
                result = callback(error)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass

    # Callback decorators

    def on_price_update(self, callback: Callable[[PriceUpdate], Any]):
        """Register a price update callback."""
        self._price_callbacks.append(callback)
        return callback

    def on_orderbook_update(self, callback: Callable[[OrderbookUpdate], Any]):
        """Register an orderbook update callback."""
        self._orderbook_callbacks.append(callback)
        return callback

    def on_error(self, callback: Callable[[Exception], Any]):
        """Register an error callback."""
        self._error_callbacks.append(callback)
        return callback

    def on_connect(self, callback: Callable[[], Any]):
        """Register a connect callback."""
        self._connect_callbacks.append(callback)
        return callback

    def on_disconnect(self, callback: Callable[[], Any]):
        """Register a disconnect callback."""
        self._disconnect_callbacks.append(callback)
        return callback

    @property
    def is_connected(self) -> bool:
        """Check if connected."""
        return self._ws is not None and self._running

    @property
    def subscriptions(self) -> Set[str]:
        """Get current subscriptions."""
        return self._subscriptions.copy()

    @property
    def state(self) -> ConnectionState:
        """Get current connection state."""
        return self._state

    @property
    def stats(self) -> Dict[str, Any]:
        """Get connection statistics."""
        uptime = None
        if self._connected_at and self._state == ConnectionState.CONNECTED:
            uptime = (datetime.now() - self._connected_at).total_seconds()

        return {
            "connected": self.is_connected,
            "state": self._state.value,
            "subscriptions": len(self._subscriptions),
            "messages_received": self._messages_received,
            "last_message_time": (
                self._last_message_time.isoformat() if self._last_message_time else None
            ),
            "connected_at": (self._connected_at.isoformat() if self._connected_at else None),
            "uptime_seconds": uptime,
            "reconnect_attempts": self._reconnect_count,
            "total_reconnects": self._total_reconnects,
        }


# Convenience function to create and connect
async def create_websocket_client(
    market_ids: Optional[List[str]] = None,
    on_price: Optional[Callable[[PriceUpdate], Any]] = None,
) -> WebSocketClient:
    """
    Create and connect a WebSocket client.

    Args:
        market_ids: Markets to subscribe to
        on_price: Price update callback

    Returns:
        Connected WebSocketClient
    """
    client = WebSocketClient()

    if on_price:
        client.on_price_update(on_price)

    await client.connect()

    if market_ids:
        await client.subscribe(market_ids)

    return client
