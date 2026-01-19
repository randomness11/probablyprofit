"""
Mock Exchange for Testing

Simulates exchange behavior for integration testing:
- Order placement with configurable fill behavior
- Partial fills
- Latency simulation
- Error injection
"""

import asyncio
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from loguru import logger


class FillBehavior(str, Enum):
    """How orders should be filled."""

    INSTANT = "instant"  # Fill immediately
    PARTIAL = "partial"  # Partial fill, then maybe more
    DELAYED = "delayed"  # Fill after delay
    REJECT = "reject"  # Reject the order
    TIMEOUT = "timeout"  # Never respond


@dataclass
class MockOrder:
    """Represents an order in the mock exchange."""

    order_id: str
    market_id: str
    outcome: str
    side: str
    size: float
    price: float
    status: str = "open"
    filled_size: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    fills: List[Dict] = field(default_factory=list)


@dataclass
class MockPosition:
    """Represents a position in the mock exchange."""

    market_id: str
    outcome: str
    size: float
    avg_price: float


class MockExchangeClient:
    """
    Mock exchange client for testing.

    Simulates Polymarket API behavior without real API calls.
    """

    def __init__(
        self,
        default_fill_behavior: FillBehavior = FillBehavior.INSTANT,
        latency_ms: int = 0,
        fill_probability: float = 1.0,
        partial_fill_pct: float = 0.5,
    ):
        """
        Initialize mock exchange.

        Args:
            default_fill_behavior: How orders are filled by default
            latency_ms: Simulated latency in milliseconds
            fill_probability: Probability of order being filled (0-1)
            partial_fill_pct: What fraction is filled in partial mode
        """
        self.default_fill_behavior = default_fill_behavior
        self.latency_ms = latency_ms
        self.fill_probability = fill_probability
        self.partial_fill_pct = partial_fill_pct

        # State
        self.orders: Dict[str, MockOrder] = {}
        self.positions: Dict[str, MockPosition] = {}
        self.balance: float = 10000.0

        # Callbacks for testing
        self._on_order_placed: Optional[Callable] = None
        self._on_fill: Optional[Callable] = None

        # Error injection
        self._inject_errors: bool = False
        self._error_rate: float = 0.0

        logger.debug("MockExchangeClient initialized")

    async def _simulate_latency(self):
        """Simulate network latency."""
        if self.latency_ms > 0:
            await asyncio.sleep(self.latency_ms / 1000.0)

    def _maybe_inject_error(self):
        """Maybe raise an error for testing error handling."""
        if self._inject_errors and random.random() < self._error_rate:
            raise Exception("Injected error for testing")

    async def place_order(
        self,
        market_id: str,
        outcome: str,
        side: str,
        size: float,
        price: float,
        order_type: str = "LIMIT",
        fill_behavior: Optional[FillBehavior] = None,
    ) -> MockOrder:
        """
        Place an order on the mock exchange.

        Args:
            market_id: Market to trade
            outcome: YES or NO
            side: BUY or SELL
            size: Order size
            price: Limit price
            order_type: Order type
            fill_behavior: Override default fill behavior

        Returns:
            MockOrder with order details
        """
        await self._simulate_latency()
        self._maybe_inject_error()

        behavior = fill_behavior or self.default_fill_behavior

        # Handle rejection
        if behavior == FillBehavior.REJECT:
            raise Exception("Order rejected by exchange")

        # Handle timeout
        if behavior == FillBehavior.TIMEOUT:
            await asyncio.sleep(60)  # Long timeout
            raise asyncio.TimeoutError("Order timed out")

        # Create order
        order = MockOrder(
            order_id=f"mock_{uuid.uuid4().hex[:12]}",
            market_id=market_id,
            outcome=outcome,
            side=side.upper(),
            size=size,
            price=price,
        )

        self.orders[order.order_id] = order

        # Notify callback
        if self._on_order_placed:
            self._on_order_placed(order)

        # Handle fills based on behavior
        if behavior == FillBehavior.INSTANT:
            await self._fill_order(order, size)
        elif behavior == FillBehavior.PARTIAL:
            partial_size = size * self.partial_fill_pct
            await self._fill_order(order, partial_size)
        elif behavior == FillBehavior.DELAYED:
            asyncio.create_task(self._delayed_fill(order, size))

        logger.debug(f"Mock order placed: {order.order_id} {side} {size}@{price}")
        return order

    async def _fill_order(self, order: MockOrder, fill_size: float):
        """Fill an order (or part of it)."""
        if fill_size <= 0 or order.status in ("filled", "cancelled"):
            return

        # Random fill probability
        if random.random() > self.fill_probability:
            return

        fill_price = order.price  # Fill at limit price
        fill = {
            "fill_id": f"fill_{uuid.uuid4().hex[:8]}",
            "size": fill_size,
            "price": fill_price,
            "timestamp": datetime.now(),
        }

        order.fills.append(fill)
        order.filled_size += fill_size

        if order.filled_size >= order.size:
            order.status = "filled"
        else:
            order.status = "partial"

        # Update position
        self._update_position(order, fill_size, fill_price)

        # Notify callback
        if self._on_fill:
            self._on_fill(order, fill)

        logger.debug(f"Mock fill: {order.order_id} {fill_size}@{fill_price}")

    async def _delayed_fill(self, order: MockOrder, size: float, delay_ms: int = 500):
        """Fill order after a delay."""
        await asyncio.sleep(delay_ms / 1000.0)
        await self._fill_order(order, size)

    def _update_position(self, order: MockOrder, size: float, price: float):
        """Update position after fill."""
        key = f"{order.market_id}_{order.outcome}"

        if key in self.positions:
            pos = self.positions[key]
            if order.side == "BUY":
                new_size = pos.size + size
                if new_size != 0:
                    pos.avg_price = (pos.avg_price * pos.size + price * size) / new_size
                pos.size = new_size
            else:  # SELL
                pos.size -= size
        else:
            if order.side == "BUY":
                self.positions[key] = MockPosition(
                    market_id=order.market_id,
                    outcome=order.outcome,
                    size=size,
                    avg_price=price,
                )

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        await self._simulate_latency()
        self._maybe_inject_error()

        if order_id not in self.orders:
            raise Exception(f"Order {order_id} not found")

        order = self.orders[order_id]
        if order.status in ("filled", "cancelled"):
            return False

        order.status = "cancelled"
        logger.debug(f"Mock order cancelled: {order_id}")
        return True

    async def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Get order status."""
        await self._simulate_latency()

        if order_id not in self.orders:
            return None

        order = self.orders[order_id]
        return {
            "order_id": order.order_id,
            "status": order.status,
            "filled_size": order.filled_size,
            "remaining_size": order.size - order.filled_size,
        }

    async def get_positions(self) -> List[MockPosition]:
        """Get all open positions."""
        await self._simulate_latency()
        return [p for p in self.positions.values() if p.size != 0]

    async def get_balance(self) -> float:
        """Get account balance."""
        await self._simulate_latency()
        return self.balance

    async def close(self):
        """Close the client (no-op for mock)."""
        pass

    # Testing utilities

    def set_fill_behavior(self, behavior: FillBehavior):
        """Change default fill behavior."""
        self.default_fill_behavior = behavior

    def inject_errors(self, rate: float = 0.1):
        """Enable error injection for testing."""
        self._inject_errors = True
        self._error_rate = rate

    def disable_error_injection(self):
        """Disable error injection."""
        self._inject_errors = False

    def on_order_placed(self, callback: Callable):
        """Register callback for order placement."""
        self._on_order_placed = callback

    def on_fill(self, callback: Callable):
        """Register callback for fills."""
        self._on_fill = callback

    def reset(self):
        """Reset all state."""
        self.orders.clear()
        self.positions.clear()
        self.balance = 10000.0


# Factory function
def create_mock_client(**kwargs) -> MockExchangeClient:
    """Create a mock exchange client."""
    return MockExchangeClient(**kwargs)
