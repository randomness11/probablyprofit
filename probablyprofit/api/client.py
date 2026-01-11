"""
Polymarket API Client

Provides a clean wrapper around the Polymarket CLOB API.
Includes retry logic and circuit breakers for resilience.
"""

import asyncio
import json
from typing import Any, Dict, List, Optional
from datetime import datetime
from decimal import Decimal

import httpx
from loguru import logger
from pydantic import BaseModel

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import OrderArgs, OrderType, ApiCreds
    params_avail = True
except ImportError:
    ClobClient = None
    OrderArgs = None
    OrderType = None
    params_avail = False
    logger.warning("py-clob-client not installed. Trading functionality will be limited.")

from probablyprofit.api.exceptions import (
    APIException,
    NetworkException,
    RateLimitException,
    ValidationException,
    OrderException,
)
from probablyprofit.utils.validators import (
    validate_price,
    validate_positive,
    validate_non_negative,
    validate_side,
)
from probablyprofit.utils.resilience import (
    retry,
    CircuitBreaker,
    RateLimiter,
)
from probablyprofit.utils.cache import AsyncTTLCache, market_cache, price_cache
from probablyprofit.api.async_wrapper import run_sync, AsyncClientWrapper

# Circuit breakers for different API endpoints
_gamma_circuit = CircuitBreaker("polymarket-gamma", failure_threshold=5, timeout=60.0)
_clob_circuit = CircuitBreaker("polymarket-clob", failure_threshold=5, timeout=60.0)

# Rate limiter (Polymarket allows ~10 req/s)
_api_rate_limiter = RateLimiter("polymarket-api", calls=8, period=1.0)


class Market(BaseModel):
    """Represents a Polymarket market."""

    condition_id: str
    question: str
    description: Optional[str] = None
    end_date: datetime
    outcomes: List[str]
    outcome_prices: List[float]
    volume: float
    liquidity: float
    active: bool = True
    metadata: Dict[str, Any] = {}


class Order(BaseModel):
    """Represents an order."""

    order_id: Optional[str] = None
    market_id: str
    outcome: str
    side: str  # BUY or SELL
    size: float
    price: float
    status: str = "pending"
    filled_size: float = 0.0
    timestamp: datetime = datetime.now()


class Position(BaseModel):
    """Represents a position in a market."""

    market_id: str
    outcome: str
    size: float
    avg_price: float
    current_price: float
    pnl: float = 0.0

    @property
    def value(self) -> float:
        """Current position value."""
        return self.size * self.current_price

    @property
    def unrealized_pnl(self) -> float:
        """Unrealized profit/loss."""
        return self.size * (self.current_price - self.avg_price)


class PolymarketClient:
    """
    High-level wrapper for Polymarket CLOB API.

    Provides clean methods for:
    - Fetching market data
    - Placing and managing orders
    - Tracking positions
    - Real-time price streaming
    """

    def __init__(
        self,
        private_key: Optional[str] = None,
        chain_id: int = 137,
        testnet: bool = False,
    ):
        """
        Initialize Polymarket client.

        Args:
            private_key: Polygon private key (starts with 0x)
            chain_id: Chain ID (137 for Polygon mainnet)
            testnet: Whether to use testnet
        """
        self.chain_id = chain_id
        self.testnet = testnet
        self.client = None

        # Initialize CLOB client if credentials provided
        if private_key:
            try:
                host = "https://clob.polymarket.com" if not testnet else "https://clob-test.polymarket.com"
                self.client = ClobClient(host=host, key=private_key, chain_id=chain_id)
                
                # Auto-derive L2 API credentials
                try:
                    logger.info("🔐 Deriving API credentials from Private Key...")
                    creds = self.client.create_or_derive_api_creds()
                    self.client.set_api_creds(creds)
                    self._api_creds = creds  # Store for auth headers
                    logger.info(f"✅ Authenticated as {creds.api_key}")
                except Exception as e:
                    logger.warning(f"Failed to auto-derive credentials: {e}")
                    
            except Exception as e:
                logger.error(f"Failed to initialize CLOB client: {e}")
                self.client = None
        else:
            logger.warning("⚠️ No Private Key provided - running in READ-ONLY mode")

        # HTTP client for CLOB endpoints (orders, prices)
        self.http_client = httpx.AsyncClient(
            base_url="https://clob.polymarket.com" if not testnet else "https://clob-test.polymarket.com",
            timeout=30.0,
        )
        
        # HTTP client for Gamma API (market metadata, volume, descriptions)
        self.gamma_client = httpx.AsyncClient(
            base_url="https://gamma-api.polymarket.com",
            timeout=30.0,
        )

        # Cache for market data (now using TTL cache)
        self._market_cache: AsyncTTLCache[Market] = AsyncTTLCache(
            ttl=60.0, max_size=1000, name="polymarket-markets"
        )
        self._positions_cache: Dict[str, Position] = {}

        # Wrap sync client for async use if available
        self._async_clob = AsyncClientWrapper(self.client, timeout=30.0) if self.client else None

        # Store credentials for auth headers
        self._api_creds = None
        self._private_key = private_key

    def _get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers for API requests."""
        headers = {}
        if self._api_creds:
            headers["Authorization"] = f"Bearer {self._api_creds.api_key}"
            # Some endpoints might need additional headers
            if hasattr(self._api_creds, 'api_secret'):
                headers["X-Api-Secret"] = self._api_creds.api_secret
            if hasattr(self._api_creds, 'api_passphrase'):
                headers["X-Api-Passphrase"] = self._api_creds.api_passphrase
        return headers

    async def get_markets(
        self,
        active: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Market]:
        """
        Fetch available markets from Gamma API.

        Args:
            active: Only fetch active markets
            limit: Maximum number of markets to return
            offset: Pagination offset

        Returns:
            List of Market objects
        """
        return await self._get_markets_with_retry(active, limit, offset)

    @retry(max_attempts=3, base_delay=2.0)
    @_gamma_circuit
    async def _get_markets_with_retry(
        self,
        active: bool,
        limit: int,
        offset: int,
    ) -> List[Market]:
        """Internal method with retry and circuit breaker."""
        # Rate limit
        await _api_rate_limiter.acquire()

        try:
            # Use Gamma API for market metadata (better data than CLOB /markets)
            response = await self.gamma_client.get(
                "/markets",
                params={
                    "closed": "false",  # ONLY open markets (most important filter)
                    "limit": limit * 2,  # Fetch extra to filter out low-volume
                    "offset": offset,
                }
            )
            response.raise_for_status()
            data = response.json()

            # Gamma API returns a list directly
            if not isinstance(data, list):
                logger.warning(f"Expected list of markets, got {type(data)}")
                return []

            markets = []
            for market_data in data:
                try:
                    # STRICT FILTER: Skip closed markets
                    if market_data.get("closed", False) == True:
                        continue
                    
                    # STRICT FILTER: Must have real volume (> $100)
                    volume = float(market_data.get("volumeNum", market_data.get("volume", 0)))
                    if volume < 100:
                        continue
                    
                    condition_id = market_data.get("conditionId", "")
                    question = market_data.get("question", "Unknown")
                    description = market_data.get("description")
                    
                    # Parse end date safely
                    end_date_str = market_data.get("endDate", "")
                    try:
                        end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00")) if end_date_str else datetime.now()
                    except ValueError:
                        end_date = datetime.now()
                    
                    # Parse outcomes - Gamma returns JSON string like '["Yes", "No"]'
                    outcomes_raw = market_data.get("outcomes", '["Yes", "No"]')
                    if isinstance(outcomes_raw, str):
                        outcomes = json.loads(outcomes_raw)
                    else:
                        outcomes = outcomes_raw

                    # Parse outcome prices - Gamma returns JSON string like '["0.21", "0.79"]'
                    prices_raw = market_data.get("outcomePrices", '[0.5, 0.5]')
                    if isinstance(prices_raw, str):
                        prices_parsed = json.loads(prices_raw)
                        outcome_prices = [float(p) for p in prices_parsed]
                    elif isinstance(prices_raw, list):
                        outcome_prices = [float(p) for p in prices_raw]
                    else:
                        outcome_prices = [0.5] * len(outcomes)
                    
                    # Use volumeNum for numeric volume (Gamma provides this)
                    volume = float(market_data.get("volumeNum", market_data.get("volume", 0)))
                    liquidity = float(market_data.get("liquidityNum", market_data.get("liquidity", 0)))
                    is_active = market_data.get("active", True) and not market_data.get("closed", False)
                    
                    market = Market(
                        condition_id=condition_id,
                        question=question,
                        description=description,
                        end_date=end_date,
                        outcomes=outcomes,
                        outcome_prices=outcome_prices,
                        volume=volume,
                        liquidity=liquidity,
                        active=is_active,
                        metadata=market_data,
                    )
                    markets.append(market)
                    # Use TTL cache instead of dict
                    self._market_cache.set(market.condition_id, market)
                except Exception as parse_error:
                    logger.debug(f"Skipping market due to parse error: {parse_error}")
                    continue

            logger.info(f"Fetched {len(markets)} markets from Gamma API")
            return markets

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise RateLimitException(f"Rate limited by Polymarket: {e}")
            raise NetworkException(f"HTTP error fetching markets: {e}")
        except httpx.RequestError as e:
            raise NetworkException(f"Network error fetching markets: {e}")
        except Exception as e:
            logger.error(f"Error fetching markets: {e}")
            raise APIException(f"Failed to fetch markets: {e}")

    async def get_market(self, condition_id: str) -> Optional[Market]:
        """
        Get details for a specific market.

        Args:
            condition_id: Market condition ID

        Returns:
            Market object or None
        """
        # Check TTL cache first
        cached = self._market_cache.get(condition_id)
        if cached is not None:
            return cached

        try:
            response = await self.http_client.get(f"/markets/{condition_id}")
            response.raise_for_status()
            market_data = response.json()

            market = Market(
                condition_id=market_data["condition_id"],
                question=market_data["question"],
                description=market_data.get("description"),
                end_date=datetime.fromisoformat(market_data["end_date"]),
                outcomes=market_data["outcomes"],
                outcome_prices=market_data.get("outcome_prices", [0.5] * len(market_data["outcomes"])),
                volume=float(market_data.get("volume", 0)),
                liquidity=float(market_data.get("liquidity", 0)),
                active=market_data.get("active", True),
                metadata=market_data,
            )

            self._market_cache.set(condition_id, market)
            return market

        except Exception as e:
            logger.error(f"Error fetching market {condition_id}: {e}")
            return None

    async def get_orderbook(self, condition_id: str, outcome: str) -> Dict[str, Any]:
        """
        Get orderbook for a market outcome.

        Args:
            condition_id: Market condition ID
            outcome: Outcome name

        Returns:
            Orderbook data with bids and asks
        """
        try:
            response = await self.http_client.get(
                f"/orderbook/{condition_id}/{outcome}"
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching orderbook: {e}")
            return {"bids": [], "asks": []}

    async def place_order(
        self,
        market_id: str,
        outcome: str,
        side: str,
        size: float,
        price: float,
        order_type: str = "LIMIT",
    ) -> Optional[Order]:
        """
        Place an order with validation and resilience.

        Args:
            market_id: Market condition ID
            outcome: Outcome to bet on
            side: BUY or SELL
            size: Order size in shares
            price: Limit price (0-1)
            order_type: Order type (LIMIT, MARKET, etc.)

        Returns:
            Order object

        Raises:
            ValidationException: If input parameters are invalid
            OrderException: If order placement fails
            APIException: If API call fails
        """
        if not self.client:
            raise OrderException("Cannot place order - no API credentials provided")

        # Validate inputs BEFORE any API calls
        try:
            validate_side(side)
            validate_positive(size, "size")
            validate_price(price, "price")
        except ValidationException as e:
            logger.error(f"Invalid order parameters: {e}")
            raise

        if not market_id:
            raise ValidationException("market_id cannot be empty")
        if not outcome:
            raise ValidationException("outcome cannot be empty")

        # Rate limit orders
        await _api_rate_limiter.acquire()

        try:
            logger.info(f"Placing {side} order: {size} shares @ ${price} on {outcome}")

            # Resolve outcome name to token_id
            token_id = outcome 
            
            # Try to resolve token ID from market metadata if outcome is a name (e.g. "Yes")
            if len(outcome) < 10:  # Heuristic: names are short, token IDs are long hashes
                market = await self.get_market(market_id)
                if market:
                    try:
                        # Find index of outcome name
                        idx = market.outcomes.index(outcome)
                        
                        # Get token IDs from metadata
                        clob_ids = market.metadata.get("clobTokenIds")
                        if clob_ids:
                            if isinstance(clob_ids, str):
                                                clob_ids = json.loads(clob_ids)
                            
                            if isinstance(clob_ids, list) and idx < len(clob_ids):
                                token_id = clob_ids[idx]
                                logger.debug(f"Resolved outcome '{outcome}' to token ID {token_id}")
                    except ValueError:
                        # Outcome name not found in list, assume it might be valid or fail later
                        pass

            # Create order using CLOB client (sync method wrapped for async)
            order_args = OrderArgs(
                price=price,
                size=size,
                side=side,
                token_id=token_id,
            )

            # Use async wrapper to safely call sync method
            if self._async_clob:
                resp = await self._async_clob.create_order(order_args)
            else:
                # Fallback: run in executor
                resp = await run_sync(self.client.create_order, order_args)

            if not resp:
                raise OrderException("Empty response from order API")

            # Map response to Order object
            order = Order(
                order_id=resp.get("orderID"),
                market_id=market_id,
                outcome=outcome,
                side=side,
                size=size,
                price=price,
                status="submitted",
                timestamp=datetime.now()
            )

            logger.info(f"Order placed successfully: {order.order_id}")
            return order

        except ValidationException:
            raise
        except OrderException:
            raise
        except httpx.HTTPError as e:
            logger.error(f"Network error placing order: {e}")
            raise NetworkException(f"Network error: {e}")
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            raise OrderException(f"Order placement failed: {e}")

    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an open order.

        Args:
            order_id: Order ID to cancel

        Returns:
            True if successful
        """
        if not self.client:
            logger.error("Cannot cancel order - no API credentials provided")
            return False

        try:
            logger.info(f"Cancelling order {order_id}")
            # Use async wrapper for sync method
            if self._async_clob:
                resp = await self._async_clob.cancel(order_id)
            else:
                resp = await run_sync(self.client.cancel, order_id)
            return True
        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
            return False

    async def get_positions(self) -> List[Position]:
        """
        Get current positions from the CLOB API.

        Returns:
            List of Position objects
        """
        if not self.client:
            logger.warning("Cannot fetch positions - no API credentials")
            return []

        try:
            import asyncio

            # Rate limit
            await _api_rate_limiter.acquire()

            # Fetch positions using the REST API with timeout
            # The CLOB API provides /positions endpoint for authenticated users
            try:
                response = await asyncio.wait_for(
                    self.http_client.get(
                        "/positions",
                        headers=self._get_auth_headers(),
                        timeout=10.0
                    ),
                    timeout=15.0  # Overall timeout
                )
            except asyncio.TimeoutError:
                logger.warning("Positions fetch timed out - using cached data")
                return list(self._positions_cache.values())

            if response.status_code == 401:
                logger.warning("Unauthorized to fetch positions - check API credentials")
                return list(self._positions_cache.values())

            if response.status_code == 404:
                # No positions - return empty or cached
                return list(self._positions_cache.values())

            response.raise_for_status()
            positions_data = response.json()

            positions = []
            for pos_data in positions_data:
                try:
                    market_id = pos_data.get("asset_id", pos_data.get("market_id", ""))
                    outcome = pos_data.get("outcome", "Yes")
                    size = float(pos_data.get("size", pos_data.get("quantity", 0)))
                    avg_price = float(pos_data.get("avg_price", pos_data.get("average_price", 0.5)))
                    current_price = float(pos_data.get("current_price", pos_data.get("price", avg_price)))

                    if size > 0:  # Only include non-zero positions
                        position = Position(
                            market_id=market_id,
                            outcome=outcome,
                            size=size,
                            avg_price=avg_price,
                            current_price=current_price,
                            pnl=size * (current_price - avg_price)
                        )
                        positions.append(position)
                        self._positions_cache[f"{market_id}_{outcome}"] = position
                except Exception as parse_error:
                    logger.debug(f"Skipping position due to parse error: {parse_error}")
                    continue

            logger.debug(f"Fetched {len(positions)} positions")
            return positions

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                # No positions endpoint or no positions - return cached
                return list(self._positions_cache.values())
            logger.error(f"HTTP error fetching positions: {e}")
            return list(self._positions_cache.values())
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return list(self._positions_cache.values())

    async def get_balance(self) -> float:
        """
        Get account balance in USDC.

        Returns:
            Balance in USDC
        """
        if not self.client:
            logger.warning("Cannot fetch balance - no API credentials")
            return 0.0

        try:
            # Rate limit
            await _api_rate_limiter.acquire()

            # Method 1: Try py_clob_client's get_balance (wrap in timeout)
            if hasattr(self.client, "get_balance"):
                try:
                    import asyncio
                    # Run synchronous call with timeout
                    loop = asyncio.get_event_loop()
                    balance = await asyncio.wait_for(
                        loop.run_in_executor(None, self.client.get_balance),
                        timeout=5.0
                    )
                    if balance is not None:
                        return float(balance)
                except asyncio.TimeoutError:
                    logger.debug("get_balance() timed out")
                except Exception as e:
                    logger.debug(f"get_balance() failed: {e}")

            # Method 2: Try CLOB API /balances endpoint
            try:
                import asyncio
                response = await asyncio.wait_for(
                    self.http_client.get(
                        "/balances",
                        headers=self._get_auth_headers(),
                        timeout=5.0
                    ),
                    timeout=10.0
                )
                if response.status_code == 200:
                    data = response.json()
                    # Parse balance from response
                    if isinstance(data, dict):
                        # Try common keys
                        for key in ["balance", "usdc", "collateral", "available", "amount"]:
                            if key in data:
                                return float(data[key])
                        # Check for nested structure
                        if "usdc" in data and isinstance(data["usdc"], dict):
                            return float(data["usdc"].get("balance", 0))
                    elif isinstance(data, list) and len(data) > 0:
                        # Array of balances - find USDC
                        for bal in data:
                            if bal.get("asset") == "USDC" or bal.get("token") == "USDC":
                                return float(bal.get("balance", bal.get("amount", 0)))
                    elif isinstance(data, (int, float)):
                        return float(data)
            except asyncio.TimeoutError:
                logger.debug("REST /balances timed out")
            except Exception as e:
                logger.debug(f"REST /balances failed: {e}")

            # Method 3: Try data-api endpoint for balance
            try:
                import asyncio
                # Polymarket data API endpoint
                response = await asyncio.wait_for(
                    self.gamma_client.get(
                        f"/users/{self._api_creds.api_key if self._api_creds else 'unknown'}/balances"
                    ),
                    timeout=10.0
                )
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, dict) and "balance" in data:
                        return float(data["balance"])
            except asyncio.TimeoutError:
                logger.debug("Gamma /balances timed out")
            except Exception as e:
                logger.debug(f"Gamma /balances failed: {e}")

            # Last resort: return 0 (tracked capital used by risk manager)
            logger.warning("Could not fetch balance from API, using tracked capital")
            return 0.0

        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            return 0.0

    async def close(self) -> None:
        """Close HTTP clients."""
        await self.http_client.aclose()
        await self.gamma_client.aclose()

    async def __aenter__(self) -> "PolymarketClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()
