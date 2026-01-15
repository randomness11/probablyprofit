"""
Order Management System

Provides comprehensive order lifecycle management:
- Order tracking and status updates
- Partial fill handling
- Order modification and cancellation
- Order history and audit trail
"""

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from loguru import logger
from pydantic import BaseModel, Field

from probablyprofit.api.exceptions import (
    OrderCancelError,
    OrderException,
    OrderModifyError,
    OrderNotFoundError,
    PartialFillError,
    ValidationException,
)
from probablyprofit.config import get_config


class OrderStatus(str, Enum):
    """Order lifecycle states."""

    PENDING = "pending"  # Created, not yet submitted
    SUBMITTED = "submitted"  # Sent to exchange
    OPEN = "open"  # Active on orderbook
    PARTIALLY_FILLED = "partial"  # Some fills received
    FILLED = "filled"  # Fully executed
    CANCELLED = "cancelled"  # User cancelled
    REJECTED = "rejected"  # Exchange rejected
    EXPIRED = "expired"  # Time-in-force expired
    FAILED = "failed"  # Submission failed


class OrderSide(str, Enum):
    """Order side."""

    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """Order types."""

    LIMIT = "LIMIT"
    MARKET = "MARKET"
    IOC = "IOC"  # Immediate or Cancel
    FOK = "FOK"  # Fill or Kill
    GTC = "GTC"  # Good Till Cancelled


class Fill(BaseModel):
    """Represents a single fill (partial execution)."""

    fill_id: str
    order_id: str
    size: float
    price: float
    fee: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.now)

    @property
    def value(self) -> float:
        """Total value of this fill."""
        return self.size * self.price


class ManagedOrder(BaseModel):
    """
    Extended order model with full lifecycle tracking.
    """

    # Core order fields
    order_id: Optional[str] = None
    client_order_id: str = Field(
        default_factory=lambda: f"pp_{int(datetime.now().timestamp() * 1000)}"
    )
    market_id: str
    outcome: str
    side: OrderSide
    order_type: OrderType = OrderType.LIMIT

    # Sizing
    size: float  # Original order size
    price: float  # Limit price (0-1 for prediction markets)
    filled_size: float = 0.0
    remaining_size: float = 0.0
    avg_fill_price: float = 0.0

    # Status
    status: OrderStatus = OrderStatus.PENDING
    status_message: Optional[str] = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now)
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=datetime.now)

    # Fills history
    fills: List[Fill] = Field(default_factory=list)

    # Fees and costs
    total_fees: float = 0.0

    # Metadata
    platform: str = "polymarket"  # polymarket, kalshi
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        """Initialize remaining_size after creation."""
        if self.remaining_size == 0.0 and self.filled_size == 0.0:
            self.remaining_size = self.size

    @property
    def is_active(self) -> bool:
        """Check if order is still active (can receive fills)."""
        return self.status in (
            OrderStatus.PENDING,
            OrderStatus.SUBMITTED,
            OrderStatus.OPEN,
            OrderStatus.PARTIALLY_FILLED,
        )

    @property
    def is_terminal(self) -> bool:
        """Check if order is in terminal state."""
        return self.status in (
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
            OrderStatus.FAILED,
        )

    @property
    def fill_ratio(self) -> float:
        """Percentage of order filled (0-1)."""
        if self.size == 0:
            return 0.0
        return self.filled_size / self.size

    @property
    def notional_value(self) -> float:
        """Total notional value of order."""
        return self.size * self.price

    @property
    def filled_value(self) -> float:
        """Total value of fills."""
        return self.filled_size * self.avg_fill_price

    def add_fill(self, fill: Fill) -> None:
        """
        Add a fill to this order.

        Updates filled_size, remaining_size, avg_fill_price, and status.
        """
        self.fills.append(fill)

        # Update aggregate fill data
        old_value = self.filled_size * self.avg_fill_price
        new_value = fill.size * fill.price
        self.filled_size += fill.size
        self.remaining_size = max(0, self.size - self.filled_size)

        # Recalculate weighted average fill price
        if self.filled_size > 0:
            self.avg_fill_price = (old_value + new_value) / self.filled_size

        # Update fees
        self.total_fees += fill.fee

        # Update status
        if self.remaining_size <= 0:
            self.status = OrderStatus.FILLED
            self.filled_at = datetime.now()
        else:
            self.status = OrderStatus.PARTIALLY_FILLED

        self.updated_at = datetime.now()

        logger.debug(
            f"Order {self.order_id} fill: {fill.size}@{fill.price:.4f} "
            f"({self.fill_ratio:.1%} filled)"
        )

    def cancel(self, reason: str = "User cancelled") -> None:
        """Mark order as cancelled."""
        if self.is_terminal:
            raise OrderCancelError(f"Cannot cancel terminal order (status={self.status})")

        self.status = OrderStatus.CANCELLED
        self.status_message = reason
        self.cancelled_at = datetime.now()
        self.updated_at = datetime.now()

    def reject(self, reason: str) -> None:
        """Mark order as rejected."""
        self.status = OrderStatus.REJECTED
        self.status_message = reason
        self.updated_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "order_id": self.order_id,
            "client_order_id": self.client_order_id,
            "market_id": self.market_id,
            "outcome": self.outcome,
            "side": self.side.value,
            "order_type": self.order_type.value,
            "size": self.size,
            "price": self.price,
            "filled_size": self.filled_size,
            "remaining_size": self.remaining_size,
            "avg_fill_price": self.avg_fill_price,
            "status": self.status.value,
            "status_message": self.status_message,
            "created_at": self.created_at.isoformat(),
            "filled_at": self.filled_at.isoformat() if self.filled_at else None,
            "fills": [f.model_dump() for f in self.fills],
            "total_fees": self.total_fees,
            "platform": self.platform,
        }


class OrderBook:
    """
    In-memory order book for tracking active orders.

    Thread-safe with LRU eviction for completed orders.
    """

    def __init__(self, max_history: int = 1000):
        """
        Initialize order book.

        Args:
            max_history: Maximum number of completed orders to keep
        """
        self.max_history = max_history
        self._lock = asyncio.Lock()

        # Active orders by order_id
        self._active: Dict[str, ManagedOrder] = {}

        # Client order ID to exchange order ID mapping
        self._client_to_exchange: Dict[str, str] = {}

        # Completed orders (LRU cache)
        self._history: OrderedDict[str, ManagedOrder] = OrderedDict()

        # Orders by market
        self._by_market: Dict[str, Set[str]] = {}

    async def add(self, order: ManagedOrder) -> None:
        """Add an order to the book."""
        async with self._lock:
            key = order.order_id or order.client_order_id
            self._active[key] = order

            # Track client to exchange mapping
            if order.order_id and order.client_order_id:
                self._client_to_exchange[order.client_order_id] = order.order_id

            # Index by market
            if order.market_id not in self._by_market:
                self._by_market[order.market_id] = set()
            self._by_market[order.market_id].add(key)

            logger.debug(f"Added order {key} to book (active: {len(self._active)})")

    async def get(self, order_id: str) -> Optional[ManagedOrder]:
        """Get order by ID (checks both exchange and client IDs)."""
        async with self._lock:
            # Try direct lookup
            if order_id in self._active:
                return self._active[order_id]

            # Try client ID mapping
            if order_id in self._client_to_exchange:
                exchange_id = self._client_to_exchange[order_id]
                return self._active.get(exchange_id)

            # Check history
            if order_id in self._history:
                return self._history[order_id]

            return None

    async def update(self, order: ManagedOrder) -> None:
        """Update an order in the book."""
        async with self._lock:
            key = order.order_id or order.client_order_id

            # If order was stored by client_order_id but now has order_id, clean up old entry
            if order.order_id and order.client_order_id and order.client_order_id in self._active:
                del self._active[order.client_order_id]
                # Update market index
                if order.market_id in self._by_market:
                    self._by_market[order.market_id].discard(order.client_order_id)
                    self._by_market[order.market_id].add(key)

            if order.is_terminal:
                # Move to history
                if key in self._active:
                    del self._active[key]

                self._history[key] = order
                self._history.move_to_end(key)

                # Evict oldest if over limit
                while len(self._history) > self.max_history:
                    self._history.popitem(last=False)

                # Remove from market index
                if order.market_id in self._by_market:
                    self._by_market[order.market_id].discard(key)
            else:
                self._active[key] = order

    async def remove(self, order_id: str) -> Optional[ManagedOrder]:
        """Remove an order from the book."""
        async with self._lock:
            order = self._active.pop(order_id, None)
            if order:
                if order.market_id in self._by_market:
                    self._by_market[order.market_id].discard(order_id)
            return order

    async def get_active(self) -> List[ManagedOrder]:
        """Get all active orders."""
        async with self._lock:
            return list(self._active.values())

    async def get_by_market(self, market_id: str) -> List[ManagedOrder]:
        """Get all orders for a specific market."""
        async with self._lock:
            order_ids = self._by_market.get(market_id, set())
            orders = []
            for oid in order_ids:
                if oid in self._active:
                    orders.append(self._active[oid])
            return orders

    async def get_history(self, limit: int = 100) -> List[ManagedOrder]:
        """Get recent order history."""
        async with self._lock:
            items = list(self._history.values())[-limit:]
            return list(reversed(items))

    @property
    def active_count(self) -> int:
        """Number of active orders."""
        return len(self._active)

    @property
    def history_count(self) -> int:
        """Number of orders in history."""
        return len(self._history)


# Callback types
OrderCallback = Callable[[ManagedOrder], None]
FillCallback = Callable[[ManagedOrder, Fill], None]


class OrderManager:
    """
    Central order management system.

    Provides:
    - Order submission and tracking
    - Status updates and fill handling
    - Order modification and cancellation
    - Callbacks for order events
    - Reconciliation with exchange
    """

    def __init__(
        self,
        client: Any = None,
        platform: str = "polymarket",
        partial_fill_timeout: float = 300.0,  # 5 minutes default
    ):
        """
        Initialize order manager.

        Args:
            client: API client (PolymarketClient or KalshiClient)
            platform: Platform name
            partial_fill_timeout: Seconds to wait before auto-canceling partial fills
        """
        self.client = client
        self.platform = platform
        self.partial_fill_timeout = partial_fill_timeout
        self.order_book = OrderBook(max_history=get_config().api.positions_cache_max_size)

        # Event callbacks
        self._on_fill: List[FillCallback] = []
        self._on_status_change: List[OrderCallback] = []
        self._on_complete: List[OrderCallback] = []
        self._on_partial_fill_timeout: List[OrderCallback] = []

        # Polling state
        self._polling = False
        self._poll_task: Optional[asyncio.Task] = None
        self._poll_interval = 5.0  # seconds

    def on_fill(self, callback: FillCallback) -> None:
        """Register callback for fill events."""
        self._on_fill.append(callback)

    def on_status_change(self, callback: OrderCallback) -> None:
        """Register callback for status change events."""
        self._on_status_change.append(callback)

    def on_complete(self, callback: OrderCallback) -> None:
        """Register callback for order completion events."""
        self._on_complete.append(callback)

    def on_partial_fill_timeout(self, callback: OrderCallback) -> None:
        """Register callback for partial fill timeout events."""
        self._on_partial_fill_timeout.append(callback)

    async def check_partial_fill_timeouts(self) -> List[ManagedOrder]:
        """
        Check for orders that have been partially filled for too long.

        Returns:
            List of orders that were cancelled due to timeout
        """
        cancelled_orders = []
        active_orders = await self.order_book.get_active()
        now = datetime.now()

        for order in active_orders:
            if order.status != OrderStatus.PARTIALLY_FILLED:
                continue

            # Find the last fill time
            if not order.fills:
                continue

            last_fill_time = max(f.timestamp for f in order.fills)
            time_since_fill = (now - last_fill_time).total_seconds()

            if time_since_fill >= self.partial_fill_timeout:
                logger.warning(
                    f"Partial fill timeout for order {order.order_id}: "
                    f"{order.fill_ratio:.1%} filled, {time_since_fill:.0f}s since last fill"
                )

                try:
                    await self.cancel_order(
                        order.order_id or order.client_order_id,
                        reason=f"Partial fill timeout ({order.fill_ratio:.1%} filled, "
                        f"remaining {order.remaining_size:.2f})",
                    )
                    cancelled_orders.append(order)

                    # Notify listeners
                    for callback in self._on_partial_fill_timeout:
                        try:
                            if asyncio.iscoroutinefunction(callback):
                                await callback(order)
                            else:
                                callback(order)
                        except Exception as e:
                            logger.warning(f"Partial fill timeout callback error: {e}")

                except Exception as e:
                    logger.error(f"Failed to cancel timed-out order {order.order_id}: {e}")

        return cancelled_orders

    async def submit_order(
        self,
        market_id: str,
        outcome: str,
        side: str,
        size: float,
        price: float,
        order_type: OrderType = OrderType.LIMIT,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ManagedOrder:
        """
        Submit a new order.

        Args:
            market_id: Market identifier
            outcome: Outcome to trade
            side: BUY or SELL
            size: Order size
            price: Limit price
            order_type: Order type
            metadata: Additional metadata

        Returns:
            ManagedOrder with status updates

        Raises:
            ValidationException: Invalid parameters
            OrderException: Submission failed
        """
        # Create managed order
        order = ManagedOrder(
            market_id=market_id,
            outcome=outcome,
            side=OrderSide(side.upper()),
            order_type=order_type,
            size=size,
            price=price,
            platform=self.platform,
            metadata=metadata or {},
        )

        # Add to book before submission
        await self.order_book.add(order)

        try:
            # Submit to exchange
            order.status = OrderStatus.SUBMITTED
            order.submitted_at = datetime.now()

            if self.client:
                # Call the appropriate client method
                if self.platform == "polymarket":
                    response = await self.client.place_order(
                        market_id=market_id,
                        outcome=outcome,
                        side=side,
                        size=size,
                        price=price,
                        order_type=order_type.value,
                    )
                    if response and response.order_id:
                        order.order_id = response.order_id
                        order.status = OrderStatus.OPEN
                elif self.platform == "kalshi":
                    # Convert price to cents for Kalshi
                    price_cents = int(price * 100)
                    response = await self.client.place_order(
                        ticker=market_id,
                        side=outcome.lower(),  # yes/no
                        action=side.lower(),  # buy/sell
                        count=int(size),
                        price=price_cents,
                    )
                    if response and response.order_id:
                        order.order_id = response.order_id
                        order.status = OrderStatus.OPEN
            else:
                # Dry run / simulation mode
                order.order_id = f"sim_{order.client_order_id}"
                order.status = OrderStatus.OPEN
                logger.info(f"[DRY RUN] Order simulated: {order.order_id}")

            order.updated_at = datetime.now()
            await self.order_book.update(order)

            # Notify listeners
            await self._notify_status_change(order)

            logger.info(
                f"Order submitted: {order.order_id} "
                f"{order.side.value} {order.size}@{order.price:.4f} {order.outcome}"
            )

            return order

        except Exception as e:
            order.status = OrderStatus.FAILED
            order.status_message = str(e)
            await self.order_book.update(order)
            logger.error(f"Order submission failed: {e}")
            raise OrderException(f"Order submission failed: {e}")

    async def cancel_order(self, order_id: str, reason: str = "User cancelled") -> bool:
        """
        Cancel an active order.

        Args:
            order_id: Order ID to cancel
            reason: Cancellation reason

        Returns:
            True if cancelled successfully

        Raises:
            OrderNotFoundError: Order not found
            OrderCancelError: Cancellation failed
        """
        order = await self.order_book.get(order_id)
        if not order:
            raise OrderNotFoundError(f"Order {order_id} not found")

        if order.is_terminal:
            raise OrderCancelError(f"Cannot cancel terminal order (status={order.status})")

        try:
            # Cancel on exchange
            if self.client and order.order_id:
                success = await self.client.cancel_order(order.order_id)
                if not success:
                    raise OrderCancelError("Exchange rejected cancellation")

            order.cancel(reason)
            await self.order_book.update(order)

            # Notify listeners
            await self._notify_status_change(order)
            await self._notify_complete(order)

            logger.info(f"Order cancelled: {order_id} ({reason})")
            return True

        except OrderCancelError:
            raise
        except Exception as e:
            logger.error(f"Cancel failed for {order_id}: {e}")
            raise OrderCancelError(f"Cancellation failed: {e}")

    async def cancel_all(self, market_id: Optional[str] = None) -> int:
        """
        Cancel all active orders, optionally filtered by market.

        Args:
            market_id: Optional market to filter by

        Returns:
            Number of orders cancelled
        """
        if market_id:
            orders = await self.order_book.get_by_market(market_id)
        else:
            orders = await self.order_book.get_active()

        cancelled = 0
        for order in orders:
            if order.is_active:
                try:
                    await self.cancel_order(
                        order.order_id or order.client_order_id, reason="Bulk cancel"
                    )
                    cancelled += 1
                except Exception as e:
                    logger.warning(f"Failed to cancel {order.order_id}: {e}")

        logger.info(f"Cancelled {cancelled} orders")
        return cancelled

    async def modify_order(
        self,
        order_id: str,
        new_price: Optional[float] = None,
        new_size: Optional[float] = None,
    ) -> ManagedOrder:
        """
        Modify an active order (cancel and replace).

        Args:
            order_id: Order to modify
            new_price: New limit price
            new_size: New order size

        Returns:
            New order replacing the old one

        Raises:
            OrderNotFoundError: Order not found
            OrderModifyError: Modification failed
        """
        order = await self.order_book.get(order_id)
        if not order:
            raise OrderNotFoundError(f"Order {order_id} not found")

        if order.is_terminal:
            raise OrderModifyError(f"Cannot modify terminal order (status={order.status})")

        # Determine new values
        price = new_price if new_price is not None else order.price
        size = new_size if new_size is not None else order.remaining_size

        try:
            # Cancel existing order
            await self.cancel_order(order_id, reason=f"Modified to {size}@{price}")

            # Submit replacement order
            new_order = await self.submit_order(
                market_id=order.market_id,
                outcome=order.outcome,
                side=order.side.value,
                size=size,
                price=price,
                order_type=order.order_type,
                metadata={
                    **order.metadata,
                    "replaces": order_id,
                },
            )

            logger.info(f"Order modified: {order_id} -> {new_order.order_id}")
            return new_order

        except Exception as e:
            logger.error(f"Modify failed for {order_id}: {e}")
            raise OrderModifyError(f"Modification failed: {e}")

    async def process_fill(
        self,
        order_id: str,
        fill_size: float,
        fill_price: float,
        fill_id: Optional[str] = None,
        fee: float = 0.0,
    ) -> ManagedOrder:
        """
        Process a fill event from the exchange.

        Args:
            order_id: Order that received the fill
            fill_size: Size filled
            fill_price: Fill price
            fill_id: Optional fill identifier
            fee: Trading fee

        Returns:
            Updated order

        Raises:
            OrderNotFoundError: Order not found
        """
        order = await self.order_book.get(order_id)
        if not order:
            raise OrderNotFoundError(f"Order {order_id} not found")

        fill = Fill(
            fill_id=fill_id or f"fill_{int(datetime.now().timestamp() * 1000)}",
            order_id=order_id,
            size=fill_size,
            price=fill_price,
            fee=fee,
        )

        old_status = order.status
        order.add_fill(fill)
        await self.order_book.update(order)

        # Notify listeners
        await self._notify_fill(order, fill)

        if order.status != old_status:
            await self._notify_status_change(order)

        if order.is_terminal:
            await self._notify_complete(order)

        return order

    async def get_order(self, order_id: str) -> Optional[ManagedOrder]:
        """Get order by ID."""
        return await self.order_book.get(order_id)

    async def get_active_orders(self) -> List[ManagedOrder]:
        """Get all active orders."""
        return await self.order_book.get_active()

    async def get_orders_for_market(self, market_id: str) -> List[ManagedOrder]:
        """Get orders for a specific market."""
        return await self.order_book.get_by_market(market_id)

    async def get_order_history(self, limit: int = 100) -> List[ManagedOrder]:
        """Get recent order history."""
        return await self.order_book.get_history(limit)

    async def reconcile(self) -> Dict[str, Any]:
        """
        Reconcile local order book with exchange.

        Fetches current order status from exchange and updates local state.

        Returns:
            Reconciliation results
        """
        if not self.client:
            return {"status": "skipped", "reason": "no_client"}

        results = {
            "checked": 0,
            "updated": 0,
            "filled": 0,
            "cancelled": 0,
            "errors": [],
        }

        active_orders = await self.order_book.get_active()

        for order in active_orders:
            if not order.order_id:
                continue

            results["checked"] += 1

            try:
                # Fetch order status from exchange
                if self.platform == "polymarket":
                    # Use the CLOB API to get order status
                    if hasattr(self.client, "get_order"):
                        status = await self.client.get_order(order.order_id)
                        if status:
                            await self._update_from_exchange(order, status)
                            results["updated"] += 1
                elif self.platform == "kalshi":
                    if hasattr(self.client, "get_order"):
                        status = await self.client.get_order(order.order_id)
                        if status:
                            await self._update_from_exchange(order, status)
                            results["updated"] += 1

            except Exception as e:
                results["errors"].append(f"{order.order_id}: {e}")

        logger.info(f"Reconciliation complete: {results}")
        return results

    async def start_polling(self, interval: float = 5.0) -> None:
        """
        Start background polling for order updates.

        Args:
            interval: Polling interval in seconds
        """
        if self._polling:
            return

        self._polling = True
        self._poll_interval = interval
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info(f"Order polling started (interval: {interval}s)")

    async def stop_polling(self) -> None:
        """Stop background polling."""
        self._polling = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        logger.info("Order polling stopped")

    async def _poll_loop(self) -> None:
        """Background polling loop."""
        while self._polling:
            try:
                # Reconcile order status with exchange
                await self.reconcile()

                # Check for partial fill timeouts
                timed_out = await self.check_partial_fill_timeouts()
                if timed_out:
                    logger.info(f"Cancelled {len(timed_out)} orders due to partial fill timeout")

            except Exception as e:
                logger.warning(f"Polling error: {e}")

            await asyncio.sleep(self._poll_interval)

    async def _update_from_exchange(
        self,
        order: ManagedOrder,
        exchange_data: Dict[str, Any],
    ) -> None:
        """Update order from exchange data."""
        # Extract status and fill info (adjust for platform)
        if self.platform == "polymarket":
            exchange_status = exchange_data.get("status", "").lower()
            filled = float(exchange_data.get("filled_size", 0))

            # Map exchange status to our status
            status_map = {
                "open": OrderStatus.OPEN,
                "filled": OrderStatus.FILLED,
                "canceled": OrderStatus.CANCELLED,
                "cancelled": OrderStatus.CANCELLED,
                "expired": OrderStatus.EXPIRED,
            }

        elif self.platform == "kalshi":
            exchange_status = exchange_data.get("status", "").lower()
            filled = float(exchange_data.get("filled_count", 0))

            status_map = {
                "resting": OrderStatus.OPEN,
                "executed": OrderStatus.FILLED,
                "canceled": OrderStatus.CANCELLED,
            }
        else:
            return

        new_status = status_map.get(exchange_status)
        if new_status and new_status != order.status:
            old_status = order.status
            order.status = new_status
            order.updated_at = datetime.now()

            if new_status == OrderStatus.FILLED:
                order.filled_at = datetime.now()
            elif new_status == OrderStatus.CANCELLED:
                order.cancelled_at = datetime.now()

            await self.order_book.update(order)
            await self._notify_status_change(order)

            if order.is_terminal:
                await self._notify_complete(order)

    async def _notify_fill(self, order: ManagedOrder, fill: Fill) -> None:
        """Notify fill callbacks."""
        for callback in self._on_fill:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(order, fill)
                else:
                    callback(order, fill)
            except Exception as e:
                logger.warning(f"Fill callback error: {e}")

    async def _notify_status_change(self, order: ManagedOrder) -> None:
        """Notify status change callbacks."""
        for callback in self._on_status_change:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(order)
                else:
                    callback(order)
            except Exception as e:
                logger.warning(f"Status callback error: {e}")

    async def _notify_complete(self, order: ManagedOrder) -> None:
        """Notify completion callbacks."""
        for callback in self._on_complete:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(order)
                else:
                    callback(order)
            except Exception as e:
                logger.warning(f"Complete callback error: {e}")


# Singleton order managers per platform
_order_managers: Dict[str, OrderManager] = {}


def get_order_manager(platform: str = "polymarket", client: Any = None) -> OrderManager:
    """
    Get or create order manager for a platform.

    Args:
        platform: Platform name
        client: Optional API client

    Returns:
        OrderManager instance
    """
    if platform not in _order_managers:
        _order_managers[platform] = OrderManager(client=client, platform=platform)
    elif client and not _order_managers[platform].client:
        _order_managers[platform].client = client

    return _order_managers[platform]
