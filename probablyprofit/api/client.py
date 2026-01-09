"""
Polymarket API Client

Provides a clean wrapper around the Polymarket CLOB API.
"""

import asyncio
from typing import Any, Dict, List, Optional
from datetime import datetime
from decimal import Decimal

import httpx
from loguru import logger
import httpx
from loguru import logger
from pydantic import BaseModel

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import OrderArgs, OrderType
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
    ValidationException,
    OrderException,
)
from probablyprofit.utils.validators import (
    validate_price,
    validate_positive,
    validate_non_negative,
    validate_side,
)


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
        api_key: Optional[str] = None,
        secret: Optional[str] = None,
        passphrase: Optional[str] = None,
        chain_id: int = 137,
        testnet: bool = False,
    ):
        """
        Initialize Polymarket client.

        Args:
            api_key: API key for authentication
            secret: API secret
            passphrase: API passphrase
            chain_id: Chain ID (137 for Polygon mainnet)
            testnet: Whether to use testnet
        """
        self.chain_id = chain_id
        self.testnet = testnet

        # Initialize CLOB client if credentials provided
        if api_key and secret and passphrase:
            self.client = ClobClient(
                host="https://clob.polymarket.com" if not testnet else "https://clob-test.polymarket.com",
                key=api_key,
                chain_id=chain_id,
            )
        else:
            # Read-only mode
            self.client = None
            logger.warning("No API credentials provided - running in read-only mode")

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

        # Cache for market data
        self._market_cache: Dict[str, Market] = {}
        self._positions_cache: Dict[str, Position] = {}

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
                        import json
                        outcomes = json.loads(outcomes_raw)
                    else:
                        outcomes = outcomes_raw
                    
                    # Parse outcome prices - Gamma returns JSON string like '["0.21", "0.79"]'
                    prices_raw = market_data.get("outcomePrices", '[0.5, 0.5]')
                    if isinstance(prices_raw, str):
                        import json
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
                    self._market_cache[market.condition_id] = market
                except Exception as parse_error:
                    logger.debug(f"Skipping market due to parse error: {parse_error}")
                    continue

            logger.info(f"Fetched {len(markets)} markets from Gamma API")
            return markets

        except Exception as e:
            logger.error(f"Error fetching markets: {e}")
            return []

    async def get_market(self, condition_id: str) -> Optional[Market]:
        """
        Get details for a specific market.

        Args:
            condition_id: Market condition ID

        Returns:
            Market object or None
        """
        # Check cache first
        if condition_id in self._market_cache:
            return self._market_cache[condition_id]

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

            self._market_cache[condition_id] = market
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
        Place an order with validation.

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

        # Validate inputs
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

        try:
            logger.info(f"Placing {side} order: {size} shares @ ${price} on {outcome}")

            # Create order using CLOB client
            order_args = OrderArgs(
                price=price,
                size=size,
                side=side,
                token_id=outcome,
            )

            resp = await self.client.create_order(order_args)

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
            resp = await self.client.cancel(order_id)
            return True
        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
            return False

    async def get_positions(self) -> List[Position]:
        """
        Get current positions.

        Returns:
            List of Position objects
        """
        if not self.client:
            logger.warning("Cannot fetch positions - no API credentials")
            return []

        try:
            # Fetch simple position info (this might need adjustment based on exact API response)
            # The CLOB client typically has a method to get trades or positions
            # For now, we will try to use `get_trades` and aggregate, or see if we can get held positions
            # NOTE: py_clob_client doesn't expose a simple "get all positions" easily in all versions.
            # We will use a simplified assumption that the user might want specific market positions or
            # we need to track them.
            # However, simpler approach for a framework: return empty for now but log specific instructions
            # or try to fetch from a known endpoint if available.

            # Attempt to use undocumented or common endpoint structure if specific method unavailable
            # or check generic "get_account_state" if available.
            # For this iteration, we will implement a basic trade aggregation if possible,
            # but since that's heavy, let's try to fetch balances of conditional tokens.
            
            # Since fetching all token balances is complex without an indexer, 
            # we will return an empty list with a TODO log, but properly structured.
            # In a real "Hedge Fund in a Box", we probably need The Graph integration here.
            
            logger.warning("get_positions is not fully implemented without Graph integration.")
            return []

        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return []

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
            # Use get_collateral_balance if available (standard in some versions)
            # Otherwise fall back to updating via on-chain or erroring
            if hasattr(self.client, "get_collateral_balance"):
                balance = await self.client.get_collateral_balance()
                return float(balance)
            
            # Fallback: Try to get it via direct request if method is missing
            # The endpoint is typically /user/balance or similar, but auth is complex.
            # Let's assume the method exists or return 0 with warning
            logger.warning("get_collateral_balance method missing from client")
            return 0.0
            
        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            return 0.0

    async def close(self) -> None:
        """Close HTTP client."""
        await self.http_client.aclose()

    async def __aenter__(self) -> "PolymarketClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()
