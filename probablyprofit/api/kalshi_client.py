"""
Kalshi API Client

Provides a complete wrapper around the Kalshi API for prediction market trading.
Includes order management, position tracking, and market data.

Kalshi uses RSA key authentication and prices in cents (1-99).
"""

import asyncio
import base64
import hashlib
import time
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from loguru import logger
from pydantic import BaseModel, Field

try:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    logger.debug("cryptography not installed - RSA signing unavailable")

try:
    from kalshi_python_async import Configuration
    from kalshi_python_async import KalshiClient as KalshiSDK

    SDK_AVAILABLE = True
except ImportError:
    Configuration = None
    KalshiSDK = None
    SDK_AVAILABLE = False

from probablyprofit.api.exceptions import (
    APIException,
    AuthenticationException,
    NetworkException,
    OrderException,
    OrderNotFoundError,
    RateLimitException,
    ValidationException,
)
from probablyprofit.config import get_config


class LRUCache(OrderedDict):
    """Simple LRU cache with max size limit."""

    def __init__(self, max_size: int = 100):
        super().__init__()
        self.max_size = max_size

    def get(self, key: str, default: Any = None) -> Any:
        if key in self:
            self.move_to_end(key)
            return self[key]
        return default

    def set(self, key: str, value: Any) -> None:
        if key in self:
            self.move_to_end(key)
        self[key] = value
        while len(self) > self.max_size:
            self.popitem(last=False)


class KalshiMarket(BaseModel):
    """Represents a Kalshi market."""

    ticker: str  # Kalshi uses ticker instead of condition_id
    question: str
    description: Optional[str] = None
    end_date: datetime
    outcomes: List[str] = ["Yes", "No"]  # Kalshi markets are binary
    outcome_prices: List[float] = [0.5, 0.5]
    volume: float = 0.0
    liquidity: float = 0.0
    active: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # Kalshi-specific fields
    status: str = "open"  # unopened, open, closed, settled
    yes_bid: Optional[int] = None  # Cents
    yes_ask: Optional[int] = None
    no_bid: Optional[int] = None
    no_ask: Optional[int] = None
    open_interest: int = 0
    category: Optional[str] = None
    event_ticker: Optional[str] = None

    @property
    def spread(self) -> Optional[int]:
        """Yes side spread in cents."""
        if self.yes_bid and self.yes_ask:
            return self.yes_ask - self.yes_bid
        return None

    @property
    def mid_price(self) -> float:
        """Mid price as probability (0-1)."""
        if self.yes_bid and self.yes_ask:
            return (self.yes_bid + self.yes_ask) / 200
        return 0.5


class KalshiOrder(BaseModel):
    """Represents a Kalshi order."""

    order_id: Optional[str] = None
    client_order_id: Optional[str] = None
    ticker: str
    side: str  # yes or no
    action: str  # buy or sell
    count: int  # number of contracts
    price: int  # price in cents
    type: str = "limit"  # limit or market
    status: str = "pending"  # resting, canceled, executed, pending
    filled_count: int = 0
    remaining_count: int = 0
    created_at: datetime = Field(default_factory=datetime.now)
    expiration_ts: Optional[int] = None  # Unix timestamp

    def model_post_init(self, __context: Any) -> None:
        if self.remaining_count == 0:
            self.remaining_count = self.count - self.filled_count

    @property
    def is_active(self) -> bool:
        return self.status in ("pending", "resting")

    @property
    def fill_ratio(self) -> float:
        if self.count == 0:
            return 0.0
        return self.filled_count / self.count

    @property
    def notional_value(self) -> float:
        """Dollar value of order."""
        return self.count * self.price / 100


class KalshiFill(BaseModel):
    """Represents a trade fill on Kalshi."""

    trade_id: str
    order_id: str
    ticker: str
    side: str
    action: str
    count: int
    price: int  # cents
    is_taker: bool = False
    created_at: datetime = Field(default_factory=datetime.now)

    @property
    def value(self) -> float:
        """Dollar value of fill."""
        return self.count * self.price / 100


class KalshiPosition(BaseModel):
    """Represents a position in a Kalshi market."""

    ticker: str
    side: str  # yes or no (which side you hold)
    position: int  # number of contracts held (can be negative for short)
    avg_price: float  # average entry price in cents
    current_price: float  # current market price in cents
    market_exposure: float = 0.0  # total exposure in cents
    realized_pnl: float = 0.0  # realized P&L in cents
    resting_orders_count: int = 0

    @property
    def value(self) -> float:
        """Current position value in dollars."""
        return abs(self.position) * self.current_price / 100

    @property
    def unrealized_pnl(self) -> float:
        """Unrealized profit/loss in dollars."""
        return self.position * (self.current_price - self.avg_price) / 100

    @property
    def total_pnl(self) -> float:
        """Total P&L in dollars."""
        return (self.realized_pnl / 100) + self.unrealized_pnl


class KalshiClient:
    """
    Complete Kalshi API client for prediction market trading.

    Features:
    - RSA key authentication (native implementation)
    - Market data fetching with caching
    - Order placement, modification, and cancellation
    - Position and balance tracking
    - Trade history and fills

    Kalshi API uses:
    - Prices in cents (1-99)
    - RSA-signed requests for authentication
    - Binary markets (Yes/No outcomes)
    """

    # API endpoints
    PROD_URL = "https://api.elections.kalshi.com"
    DEMO_URL = "https://demo-api.kalshi.com"
    API_VERSION = "/trade-api/v2"

    def __init__(
        self,
        api_key_id: Optional[str] = None,
        private_key_path: Optional[str] = None,
        private_key_pem: Optional[str] = None,
        demo: bool = False,
    ):
        """
        Initialize Kalshi client.

        Args:
            api_key_id: API key ID from Kalshi dashboard
            private_key_path: Path to RSA private key file (.pem)
            private_key_pem: RSA private key as PEM string (alternative to path)
            demo: Use demo environment (paper trading)
        """
        self.demo = demo
        self.api_key_id = api_key_id
        self._private_key = None
        self._member_id: Optional[str] = None

        # Base URL
        self.base_url = self.DEMO_URL if demo else self.PROD_URL
        self.api_base = f"{self.base_url}{self.API_VERSION}"

        # Load private key for signing
        if api_key_id and (private_key_path or private_key_pem):
            self._load_private_key(private_key_path, private_key_pem)

        # Get config for timeouts
        cfg = get_config()

        # HTTP client
        self.http_client = httpx.AsyncClient(
            base_url=self.api_base,
            timeout=cfg.api.http_timeout,
        )

        # Caches
        self._market_cache: LRUCache = LRUCache(max_size=cfg.api.market_cache_max_size)
        self._event_cache: LRUCache = LRUCache(max_size=100)
        self._order_cache: LRUCache = LRUCache(max_size=cfg.api.positions_cache_max_size)

        # Rate limiting
        self._last_request_time = 0.0
        self._min_request_interval = 0.1  # 100ms between requests

        # Log initialization
        if self._private_key:
            logger.info(f"✅ Kalshi client initialized ({'demo' if demo else 'prod'})")
        else:
            logger.warning("⚠️ Kalshi client in read-only mode (no credentials)")

    def _load_private_key(
        self,
        path: Optional[str],
        pem_string: Optional[str],
    ) -> None:
        """Load RSA private key for request signing."""
        if not CRYPTO_AVAILABLE:
            logger.error("cryptography package required for Kalshi authentication")
            logger.error("Install with: pip install cryptography")
            return

        try:
            if path:
                key_path = Path(path).expanduser()
                if not key_path.exists():
                    logger.error(f"Private key file not found: {key_path}")
                    return
                pem_data = key_path.read_bytes()
            elif pem_string:
                pem_data = pem_string.encode()
            else:
                return

            self._private_key = serialization.load_pem_private_key(
                pem_data,
                password=None,
                backend=default_backend(),
            )
            logger.debug("RSA private key loaded successfully")

        except Exception as e:
            logger.error(f"Failed to load private key: {e}")
            self._private_key = None

    def _sign_request(self, method: str, path: str, timestamp: int) -> str:
        """
        Create RSA signature for request authentication.

        Kalshi requires: RSA-SHA256 signature of "timestamp + method + path"
        """
        if not self._private_key:
            raise AuthenticationException("Private key not loaded")

        message = f"{timestamp}{method.upper()}{path}".encode()

        signature = self._private_key.sign(
            message,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )

        return base64.b64encode(signature).decode()

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        authenticated: bool = False,
    ) -> Dict[str, Any]:
        """
        Make API request with optional authentication.

        Args:
            method: HTTP method
            path: API endpoint path
            params: Query parameters
            json_data: JSON body for POST/PUT
            authenticated: Whether to sign request

        Returns:
            Response JSON

        Raises:
            AuthenticationException: Auth failed
            RateLimitException: Rate limited
            NetworkException: Network error
            APIException: API error
        """
        # Rate limiting
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._min_request_interval:
            await asyncio.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.time()

        # Build headers
        headers: Dict[str, str] = {"Content-Type": "application/json"}

        if authenticated:
            if not self.api_key_id or not self._private_key:
                raise AuthenticationException("API credentials required")

            timestamp = int(time.time() * 1000)
            signature = self._sign_request(method, path, timestamp)

            headers["KALSHI-ACCESS-KEY"] = self.api_key_id
            headers["KALSHI-ACCESS-SIGNATURE"] = signature
            headers["KALSHI-ACCESS-TIMESTAMP"] = str(timestamp)

        try:
            response = await self.http_client.request(
                method=method,
                url=path,
                params=params,
                json=json_data,
                headers=headers,
            )

            # Handle errors
            if response.status_code == 401:
                raise AuthenticationException("Invalid API credentials")
            elif response.status_code == 403:
                raise AuthenticationException("Access forbidden - check API permissions")
            elif response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "60")
                raise RateLimitException(f"Rate limited. Retry after {retry_after}s")
            elif response.status_code == 404:
                return {}  # Return empty for not found
            elif response.status_code >= 400:
                error_msg = response.text
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error", {}).get("message", response.text)
                except Exception:
                    pass
                raise APIException(f"API error ({response.status_code}): {error_msg}")

            return response.json() if response.text else {}

        except httpx.TimeoutException:
            raise NetworkException("Request timed out")
        except httpx.RequestError as e:
            raise NetworkException(f"Network error: {e}")

    @property
    def is_authenticated(self) -> bool:
        """Check if client has valid credentials."""
        return bool(self.api_key_id and self._private_key)

    # =========================================================================
    # Account Methods
    # =========================================================================

    async def get_account(self) -> Dict[str, Any]:
        """
        Get account information including member ID.

        Returns:
            Account data
        """
        data = await self._request("GET", "/portfolio/balance", authenticated=True)
        if "member_id" in data:
            self._member_id = data["member_id"]
        return data

    async def get_balance(self) -> float:
        """
        Get account balance in USD.

        Returns:
            Available balance in dollars
        """
        try:
            data = await self._request("GET", "/portfolio/balance", authenticated=True)
            # Kalshi returns balance in cents
            balance_cents = data.get("balance", 0)
            return balance_cents / 100
        except AuthenticationException:
            logger.warning("Cannot get balance - not authenticated")
            return 0.0
        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            return 0.0

    # =========================================================================
    # Market Data Methods
    # =========================================================================

    async def get_markets(
        self,
        status: str = "open",
        limit: int = 100,
        cursor: Optional[str] = None,
        event_ticker: Optional[str] = None,
        series_ticker: Optional[str] = None,
        min_close_ts: Optional[int] = None,
        max_close_ts: Optional[int] = None,
    ) -> List[KalshiMarket]:
        """
        Get markets with filtering options.

        Args:
            status: Market status (unopened, open, closed, settled)
            limit: Max markets to return (max 1000)
            cursor: Pagination cursor
            event_ticker: Filter by event
            series_ticker: Filter by series
            min_close_ts: Minimum close timestamp
            max_close_ts: Maximum close timestamp

        Returns:
            List of KalshiMarket objects
        """
        params: Dict[str, Any] = {
            "status": status,
            "limit": min(limit, 1000),
        }

        if cursor:
            params["cursor"] = cursor
        if event_ticker:
            params["event_ticker"] = event_ticker
        if series_ticker:
            params["series_ticker"] = series_ticker
        if min_close_ts:
            params["min_close_ts"] = min_close_ts
        if max_close_ts:
            params["max_close_ts"] = max_close_ts

        data = await self._request("GET", "/markets", params=params)

        markets = []
        for market_data in data.get("markets", []):
            market = self._parse_market(market_data)
            markets.append(market)
            self._market_cache.set(market.ticker, market)

        logger.info(f"Fetched {len(markets)} Kalshi markets")
        return markets

    async def get_market(self, ticker: str, use_cache: bool = True) -> Optional[KalshiMarket]:
        """
        Get a specific market by ticker.

        Args:
            ticker: Market ticker symbol
            use_cache: Whether to check cache first

        Returns:
            KalshiMarket object or None
        """
        if use_cache:
            cached = self._market_cache.get(ticker)
            if cached:
                return cached

        data = await self._request("GET", f"/markets/{ticker}")
        if not data or "market" not in data:
            logger.warning(f"Market {ticker} not found")
            return None

        market = self._parse_market(data["market"])
        self._market_cache.set(ticker, market)
        return market

    async def get_event(self, event_ticker: str) -> Optional[Dict[str, Any]]:
        """
        Get event details (group of related markets).

        Args:
            event_ticker: Event ticker

        Returns:
            Event data or None
        """
        cached = self._event_cache.get(event_ticker)
        if cached:
            return cached

        data = await self._request("GET", f"/events/{event_ticker}")
        if data and "event" in data:
            self._event_cache.set(event_ticker, data["event"])
            return data["event"]
        return None

    async def get_orderbook(self, ticker: str, depth: int = 10) -> Dict[str, Any]:
        """
        Get orderbook for a market.

        Args:
            ticker: Market ticker
            depth: Number of price levels

        Returns:
            Orderbook with yes/no bids and asks
        """
        params = {"depth": depth}
        data = await self._request("GET", f"/markets/{ticker}/orderbook", params=params)

        return {
            "ticker": ticker,
            "yes": data.get("orderbook", {}).get("yes", []),
            "no": data.get("orderbook", {}).get("no", []),
        }

    async def get_trades(
        self,
        ticker: Optional[str] = None,
        limit: int = 100,
        cursor: Optional[str] = None,
        min_ts: Optional[int] = None,
        max_ts: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get recent trades (public market activity).

        Args:
            ticker: Optional market filter
            limit: Max trades to return
            cursor: Pagination cursor
            min_ts: Minimum timestamp
            max_ts: Maximum timestamp

        Returns:
            List of trade records
        """
        params: Dict[str, Any] = {"limit": limit}
        if ticker:
            params["ticker"] = ticker
        if cursor:
            params["cursor"] = cursor
        if min_ts:
            params["min_ts"] = min_ts
        if max_ts:
            params["max_ts"] = max_ts

        data = await self._request("GET", "/markets/trades", params=params)
        return data.get("trades", [])

    # =========================================================================
    # Order Management
    # =========================================================================

    async def place_order(
        self,
        ticker: str,
        side: str,  # "yes" or "no"
        action: str,  # "buy" or "sell"
        count: int,
        price: int,  # cents (1-99)
        order_type: str = "limit",
        client_order_id: Optional[str] = None,
        expiration_ts: Optional[int] = None,
    ) -> KalshiOrder:
        """
        Place an order on Kalshi.

        Args:
            ticker: Market ticker
            side: "yes" or "no"
            action: "buy" or "sell"
            count: Number of contracts
            price: Price in cents (1-99)
            order_type: "limit" or "market"
            client_order_id: Optional client reference ID
            expiration_ts: Optional expiration timestamp

        Returns:
            KalshiOrder object

        Raises:
            ValidationException: Invalid parameters
            OrderException: Order placement failed
        """
        # Validate inputs
        side = side.lower()
        action = action.lower()

        if side not in ("yes", "no"):
            raise ValidationException(f"Side must be 'yes' or 'no', got '{side}'")
        if action not in ("buy", "sell"):
            raise ValidationException(f"Action must be 'buy' or 'sell', got '{action}'")
        if not 1 <= price <= 99:
            raise ValidationException(f"Price must be 1-99 cents, got {price}")
        if count <= 0:
            raise ValidationException(f"Count must be positive, got {count}")

        # Build order payload
        order_data: Dict[str, Any] = {
            "ticker": ticker,
            "type": order_type,
            "action": action,
            "side": side,
            "count": count,
        }

        # Set price based on side
        if side == "yes":
            order_data["yes_price"] = price
        else:
            order_data["no_price"] = price

        if client_order_id:
            order_data["client_order_id"] = client_order_id
        else:
            order_data["client_order_id"] = f"pp_{int(time.time() * 1000)}"

        if expiration_ts:
            order_data["expiration_ts"] = expiration_ts

        try:
            response = await self._request(
                "POST",
                "/portfolio/orders",
                json_data=order_data,
                authenticated=True,
            )

            order_info = response.get("order", {})

            order = KalshiOrder(
                order_id=order_info.get("order_id"),
                client_order_id=order_data["client_order_id"],
                ticker=ticker,
                side=side,
                action=action,
                count=count,
                price=price,
                type=order_type,
                status=order_info.get("status", "resting"),
                filled_count=order_info.get("filled_count", 0),
                remaining_count=order_info.get("remaining_count", count),
            )

            # Cache the order
            if order.order_id:
                self._order_cache.set(order.order_id, order)

            logger.info(
                f"✅ Kalshi order placed: {action.upper()} {count} {side} @ {price}¢ on {ticker} "
                f"(order_id: {order.order_id})"
            )
            return order

        except ValidationException:
            raise
        except AuthenticationException:
            raise
        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            raise OrderException(f"Order placement failed: {e}")

    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.

        Args:
            order_id: Order ID to cancel

        Returns:
            True if cancelled
        """
        try:
            await self._request(
                "DELETE",
                f"/portfolio/orders/{order_id}",
                authenticated=True,
            )

            # Update cache
            cached = self._order_cache.get(order_id)
            if cached:
                cached.status = "canceled"
                self._order_cache.set(order_id, cached)

            logger.info(f"✅ Kalshi order cancelled: {order_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    async def cancel_all_orders(self, ticker: Optional[str] = None) -> int:
        """
        Cancel all open orders.

        Args:
            ticker: Optional ticker to filter by

        Returns:
            Number of orders cancelled
        """
        orders = await self.get_open_orders(ticker=ticker)
        cancelled = 0

        for order in orders:
            if order.order_id and await self.cancel_order(order.order_id):
                cancelled += 1

        logger.info(f"Cancelled {cancelled} orders")
        return cancelled

    async def modify_order(
        self,
        order_id: str,
        new_price: Optional[int] = None,
        new_count: Optional[int] = None,
    ) -> KalshiOrder:
        """
        Modify an existing order (cancel and replace).

        Args:
            order_id: Order to modify
            new_price: New price in cents
            new_count: New contract count

        Returns:
            New order
        """
        # Get existing order
        order = await self.get_order(order_id)
        if not order:
            raise OrderNotFoundError(f"Order {order_id} not found")

        # Cancel old order
        await self.cancel_order(order_id)

        # Place new order
        return await self.place_order(
            ticker=order.ticker,
            side=order.side,
            action=order.action,
            count=new_count or order.remaining_count,
            price=new_price or order.price,
            client_order_id=f"mod_{order_id}_{int(time.time())}",
        )

    async def get_order(self, order_id: str) -> Optional[KalshiOrder]:
        """
        Get order details.

        Args:
            order_id: Order ID

        Returns:
            KalshiOrder or None
        """
        # Check cache
        cached = self._order_cache.get(order_id)
        if cached:
            return cached

        data = await self._request(
            "GET",
            f"/portfolio/orders/{order_id}",
            authenticated=True,
        )

        if not data or "order" not in data:
            return None

        order_info = data["order"]
        order = KalshiOrder(
            order_id=order_info.get("order_id"),
            client_order_id=order_info.get("client_order_id"),
            ticker=order_info.get("ticker", ""),
            side=order_info.get("side", "yes"),
            action=order_info.get("action", "buy"),
            count=order_info.get("count", 0),
            price=order_info.get("yes_price") or order_info.get("no_price", 0),
            type=order_info.get("type", "limit"),
            status=order_info.get("status", "unknown"),
            filled_count=order_info.get("filled_count", 0),
            remaining_count=order_info.get("remaining_count", 0),
        )

        self._order_cache.set(order_id, order)
        return order

    async def get_open_orders(
        self,
        ticker: Optional[str] = None,
        limit: int = 100,
    ) -> List[KalshiOrder]:
        """
        Get all open orders.

        Args:
            ticker: Optional market filter
            limit: Max orders to return

        Returns:
            List of open orders
        """
        params: Dict[str, Any] = {"limit": limit, "status": "resting"}
        if ticker:
            params["ticker"] = ticker

        data = await self._request(
            "GET",
            "/portfolio/orders",
            params=params,
            authenticated=True,
        )

        orders = []
        for order_info in data.get("orders", []):
            order = KalshiOrder(
                order_id=order_info.get("order_id"),
                client_order_id=order_info.get("client_order_id"),
                ticker=order_info.get("ticker", ""),
                side=order_info.get("side", "yes"),
                action=order_info.get("action", "buy"),
                count=order_info.get("count", 0),
                price=order_info.get("yes_price") or order_info.get("no_price", 0),
                type=order_info.get("type", "limit"),
                status=order_info.get("status", "resting"),
                filled_count=order_info.get("filled_count", 0),
                remaining_count=order_info.get("remaining_count", 0),
            )
            orders.append(order)
            if order.order_id:
                self._order_cache.set(order.order_id, order)

        return orders

    async def get_fills(
        self,
        ticker: Optional[str] = None,
        order_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[KalshiFill]:
        """
        Get user's trade fills.

        Args:
            ticker: Optional market filter
            order_id: Optional order filter
            limit: Max fills to return

        Returns:
            List of fills
        """
        params: Dict[str, Any] = {"limit": limit}
        if ticker:
            params["ticker"] = ticker
        if order_id:
            params["order_id"] = order_id

        data = await self._request(
            "GET",
            "/portfolio/fills",
            params=params,
            authenticated=True,
        )

        fills = []
        for fill_info in data.get("fills", []):
            fill = KalshiFill(
                trade_id=fill_info.get("trade_id", ""),
                order_id=fill_info.get("order_id", ""),
                ticker=fill_info.get("ticker", ""),
                side=fill_info.get("side", "yes"),
                action=fill_info.get("action", "buy"),
                count=fill_info.get("count", 0),
                price=fill_info.get("yes_price") or fill_info.get("no_price", 0),
                is_taker=fill_info.get("is_taker", False),
            )
            fills.append(fill)

        return fills

    # =========================================================================
    # Position Management
    # =========================================================================

    async def get_positions(
        self,
        ticker: Optional[str] = None,
        event_ticker: Optional[str] = None,
        settlement_status: str = "unsettled",
    ) -> List[KalshiPosition]:
        """
        Get current positions.

        Args:
            ticker: Optional market filter
            event_ticker: Optional event filter
            settlement_status: "settled", "unsettled", or "all"

        Returns:
            List of positions
        """
        params: Dict[str, Any] = {"settlement_status": settlement_status}
        if ticker:
            params["ticker"] = ticker
        if event_ticker:
            params["event_ticker"] = event_ticker

        try:
            data = await self._request(
                "GET",
                "/portfolio/positions",
                params=params,
                authenticated=True,
            )

            positions = []
            for pos_info in data.get("market_positions", []):
                # Get current price from market
                current_price = 50  # default mid
                mkt = await self.get_market(pos_info.get("ticker", ""))
                if mkt:
                    current_price = int(mkt.mid_price * 100)

                position = KalshiPosition(
                    ticker=pos_info.get("ticker", ""),
                    side="yes" if pos_info.get("position", 0) > 0 else "no",
                    position=pos_info.get("position", 0),
                    avg_price=pos_info.get("market_exposure", 0)
                    / max(abs(pos_info.get("position", 1)), 1),
                    current_price=current_price,
                    market_exposure=pos_info.get("market_exposure", 0),
                    realized_pnl=pos_info.get("realized_pnl", 0),
                    resting_orders_count=pos_info.get("resting_orders_count", 0),
                )
                positions.append(position)

            return positions

        except AuthenticationException:
            logger.warning("Cannot get positions - not authenticated")
            return []
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return []

    # =========================================================================
    # Exchange Status & Utilities
    # =========================================================================

    async def get_exchange_status(self) -> Dict[str, Any]:
        """
        Get current exchange operational status.

        Returns:
            Status dict with exchange_active, trading_active, etc.
        """
        try:
            data = await self._request("GET", "/exchange/status")
            return {
                "exchange_active": data.get("exchange_active", False),
                "trading_active": data.get("trading_active", False),
            }
        except Exception as e:
            logger.warning(f"Could not fetch exchange status: {e}")
            return {
                "exchange_active": None,
                "trading_active": None,
                "status_unknown": True,
                "error": str(e),
            }

    async def get_exchange_schedule(self) -> Dict[str, Any]:
        """
        Get exchange trading schedule.

        Returns:
            Schedule information
        """
        return await self._request("GET", "/exchange/schedule")

    async def search_markets(
        self,
        query: str,
        limit: int = 20,
    ) -> List[KalshiMarket]:
        """
        Search markets by text query.

        Args:
            query: Search query
            limit: Max results

        Returns:
            Matching markets
        """
        # Kalshi doesn't have a dedicated search endpoint,
        # so we fetch markets and filter client-side
        all_markets = await self.get_markets(limit=200)

        query_lower = query.lower()
        matches = [
            m
            for m in all_markets
            if query_lower in m.question.lower()
            or query_lower in (m.description or "").lower()
            or query_lower in m.ticker.lower()
        ]

        return matches[:limit]

    def _parse_market(self, data: Dict[str, Any]) -> KalshiMarket:
        """Parse Kalshi API market data into KalshiMarket object."""
        ticker = data.get("ticker", "")
        question = data.get("title", "") or data.get("subtitle", ticker)

        # Parse dates
        close_time = data.get("close_time") or data.get("expiration_time")
        try:
            if close_time:
                end_date = datetime.fromisoformat(close_time.replace("Z", "+00:00"))
            else:
                end_date = datetime.now()
        except ValueError:
            end_date = datetime.now()

        # Extract prices (in cents)
        yes_bid = data.get("yes_bid")
        yes_ask = data.get("yes_ask")
        no_bid = data.get("no_bid")
        no_ask = data.get("no_ask")

        # Calculate probabilities (0-1 scale)
        if yes_bid and yes_ask:
            yes_price = (yes_bid + yes_ask) / 200
        elif yes_bid:
            yes_price = yes_bid / 100
        elif yes_ask:
            yes_price = yes_ask / 100
        else:
            yes_price = 0.5

        no_price = 1.0 - yes_price

        return KalshiMarket(
            ticker=ticker,
            question=question,
            description=data.get("rules", ""),
            end_date=end_date,
            outcomes=["Yes", "No"],
            outcome_prices=[yes_price, no_price],
            volume=float(data.get("volume", 0)),
            liquidity=float(data.get("liquidity", 0)),
            active=data.get("status") == "open",
            status=data.get("status", "unknown"),
            yes_bid=yes_bid,
            yes_ask=yes_ask,
            no_bid=no_bid,
            no_ask=no_ask,
            open_interest=data.get("open_interest", 0),
            category=data.get("category"),
            event_ticker=data.get("event_ticker"),
            metadata=data,
        )

    # =========================================================================
    # Context Management
    # =========================================================================

    async def close(self) -> None:
        """Close HTTP clients and cleanup resources."""
        await self.http_client.aclose()
        logger.info("Kalshi client closed")

    async def __aenter__(self) -> "KalshiClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()
