"""
Tests for the Order Management System.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from probablyprofit.api.exceptions import OrderCancelError, OrderModifyError, OrderNotFoundError
from probablyprofit.api.order_manager import (
    Fill,
    ManagedOrder,
    OrderBook,
    OrderManager,
    OrderSide,
    OrderStatus,
    OrderType,
)


class TestManagedOrder:
    """Tests for ManagedOrder model."""

    def test_order_creation(self):
        """Test basic order creation."""
        order = ManagedOrder(
            market_id="0x123",
            outcome="Yes",
            side=OrderSide.BUY,
            size=100.0,
            price=0.55,
        )

        assert order.market_id == "0x123"
        assert order.outcome == "Yes"
        assert order.side == OrderSide.BUY
        assert order.size == 100.0
        assert order.price == 0.55
        assert order.status == OrderStatus.PENDING
        assert order.filled_size == 0.0
        assert order.remaining_size == 100.0

    def test_order_is_active(self):
        """Test is_active property."""
        order = ManagedOrder(
            market_id="0x123",
            outcome="Yes",
            side=OrderSide.BUY,
            size=100.0,
            price=0.5,
        )

        # Pending is active
        assert order.is_active is True

        # Submitted is active
        order.status = OrderStatus.SUBMITTED
        assert order.is_active is True

        # Filled is not active
        order.status = OrderStatus.FILLED
        assert order.is_active is False

        # Cancelled is not active
        order.status = OrderStatus.CANCELLED
        assert order.is_active is False

    def test_order_add_fill(self):
        """Test adding fills to an order."""
        order = ManagedOrder(
            market_id="0x123",
            outcome="Yes",
            side=OrderSide.BUY,
            size=100.0,
            price=0.5,
        )

        # Add partial fill
        fill1 = Fill(
            fill_id="fill1",
            order_id="order1",
            size=40.0,
            price=0.48,
            fee=0.02,
        )
        order.add_fill(fill1)

        assert order.filled_size == 40.0
        assert order.remaining_size == 60.0
        assert order.avg_fill_price == pytest.approx(0.48)
        assert order.status == OrderStatus.PARTIALLY_FILLED
        assert len(order.fills) == 1
        assert order.total_fees == 0.02

        # Add another fill
        fill2 = Fill(
            fill_id="fill2",
            order_id="order1",
            size=60.0,
            price=0.52,
            fee=0.03,
        )
        order.add_fill(fill2)

        assert order.filled_size == 100.0
        assert order.remaining_size == 0.0
        assert order.status == OrderStatus.FILLED
        assert order.filled_at is not None

        # Check weighted average price: (40*0.48 + 60*0.52) / 100 = 0.504
        assert order.avg_fill_price == pytest.approx(0.504)

    def test_order_fill_ratio(self):
        """Test fill_ratio calculation."""
        order = ManagedOrder(
            market_id="0x123",
            outcome="Yes",
            side=OrderSide.BUY,
            size=100.0,
            price=0.5,
        )

        assert order.fill_ratio == 0.0

        fill = Fill(
            fill_id="fill1",
            order_id="order1",
            size=25.0,
            price=0.5,
        )
        order.add_fill(fill)

        assert order.fill_ratio == pytest.approx(0.25)

    def test_order_cancel(self):
        """Test order cancellation."""
        order = ManagedOrder(
            market_id="0x123",
            outcome="Yes",
            side=OrderSide.BUY,
            size=100.0,
            price=0.5,
        )
        order.status = OrderStatus.OPEN

        order.cancel("Test cancellation")

        assert order.status == OrderStatus.CANCELLED
        assert order.status_message == "Test cancellation"
        assert order.cancelled_at is not None

    def test_cannot_cancel_terminal_order(self):
        """Test that terminal orders cannot be cancelled."""
        order = ManagedOrder(
            market_id="0x123",
            outcome="Yes",
            side=OrderSide.BUY,
            size=100.0,
            price=0.5,
        )
        order.status = OrderStatus.FILLED

        with pytest.raises(OrderCancelError):
            order.cancel("Should fail")

    def test_order_to_dict(self):
        """Test serialization."""
        order = ManagedOrder(
            market_id="0x123",
            outcome="Yes",
            side=OrderSide.BUY,
            size=100.0,
            price=0.5,
        )

        data = order.to_dict()

        assert data["market_id"] == "0x123"
        assert data["outcome"] == "Yes"
        assert data["side"] == "BUY"
        assert data["size"] == 100.0
        assert data["price"] == 0.5
        assert data["status"] == "pending"


class TestOrderBook:
    """Tests for OrderBook."""

    @pytest.mark.asyncio
    async def test_add_and_get_order(self):
        """Test adding and retrieving orders."""
        book = OrderBook(max_history=10)

        order = ManagedOrder(
            order_id="order1",
            market_id="0x123",
            outcome="Yes",
            side=OrderSide.BUY,
            size=100.0,
            price=0.5,
        )

        await book.add(order)

        retrieved = await book.get("order1")
        assert retrieved is not None
        assert retrieved.order_id == "order1"

    @pytest.mark.asyncio
    async def test_get_active_orders(self):
        """Test getting all active orders."""
        book = OrderBook()

        order1 = ManagedOrder(
            order_id="order1",
            market_id="0x123",
            outcome="Yes",
            side=OrderSide.BUY,
            size=100.0,
            price=0.5,
        )
        order2 = ManagedOrder(
            order_id="order2",
            market_id="0x456",
            outcome="No",
            side=OrderSide.SELL,
            size=50.0,
            price=0.6,
        )

        await book.add(order1)
        await book.add(order2)

        active = await book.get_active()
        assert len(active) == 2

    @pytest.mark.asyncio
    async def test_orders_move_to_history(self):
        """Test that terminal orders move to history."""
        book = OrderBook(max_history=5)

        order = ManagedOrder(
            order_id="order1",
            market_id="0x123",
            outcome="Yes",
            side=OrderSide.BUY,
            size=100.0,
            price=0.5,
        )

        await book.add(order)
        assert book.active_count == 1

        # Mark as filled
        order.status = OrderStatus.FILLED
        await book.update(order)

        assert book.active_count == 0
        assert book.history_count == 1

        # Should still be retrievable
        retrieved = await book.get("order1")
        assert retrieved is not None

    @pytest.mark.asyncio
    async def test_get_orders_by_market(self):
        """Test filtering orders by market."""
        book = OrderBook()

        order1 = ManagedOrder(
            order_id="order1",
            market_id="market_A",
            outcome="Yes",
            side=OrderSide.BUY,
            size=100.0,
            price=0.5,
        )
        order2 = ManagedOrder(
            order_id="order2",
            market_id="market_B",
            outcome="Yes",
            side=OrderSide.BUY,
            size=100.0,
            price=0.5,
        )
        order3 = ManagedOrder(
            order_id="order3",
            market_id="market_A",
            outcome="No",
            side=OrderSide.SELL,
            size=50.0,
            price=0.6,
        )

        await book.add(order1)
        await book.add(order2)
        await book.add(order3)

        market_a_orders = await book.get_by_market("market_A")
        assert len(market_a_orders) == 2

        market_b_orders = await book.get_by_market("market_B")
        assert len(market_b_orders) == 1


class TestOrderManager:
    """Tests for OrderManager."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock client."""
        client = MagicMock()
        # Use side_effect to return unique order IDs
        order_counter = [0]

        def make_order_response():
            order_counter[0] += 1
            return MagicMock(order_id=f"ex_order_{order_counter[0]}")

        client.place_order = AsyncMock(side_effect=lambda *args, **kwargs: make_order_response())
        client.cancel_order = AsyncMock(return_value=True)
        return client

    @pytest.fixture
    def order_manager(self, mock_client):
        """Create an order manager with mock client."""
        return OrderManager(client=mock_client, platform="polymarket")

    @pytest.mark.asyncio
    async def test_submit_order(self, order_manager):
        """Test submitting an order."""
        order = await order_manager.submit_order(
            market_id="0x123",
            outcome="Yes",
            side="BUY",
            size=100.0,
            price=0.5,
        )

        assert order is not None
        assert order.market_id == "0x123"
        assert order.outcome == "Yes"
        assert order.side == OrderSide.BUY
        assert order.size == 100.0
        assert order.price == 0.5
        assert order.status in (OrderStatus.OPEN, OrderStatus.SUBMITTED)

    @pytest.mark.asyncio
    async def test_cancel_order(self, order_manager):
        """Test cancelling an order."""
        # First submit an order
        order = await order_manager.submit_order(
            market_id="0x123",
            outcome="Yes",
            side="BUY",
            size=100.0,
            price=0.5,
        )

        # Cancel it
        order_id = order.order_id or order.client_order_id
        result = await order_manager.cancel_order(order_id)

        assert result is True

        # Verify status
        updated = await order_manager.get_order(order_id)
        assert updated.status == OrderStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_order(self, order_manager):
        """Test cancelling a non-existent order."""
        with pytest.raises(OrderNotFoundError):
            await order_manager.cancel_order("nonexistent_order")

    @pytest.mark.asyncio
    async def test_process_fill(self, order_manager):
        """Test processing fills."""
        order = await order_manager.submit_order(
            market_id="0x123",
            outcome="Yes",
            side="BUY",
            size=100.0,
            price=0.5,
        )

        order_id = order.order_id or order.client_order_id

        # Process a partial fill
        updated = await order_manager.process_fill(
            order_id=order_id,
            fill_size=30.0,
            fill_price=0.48,
        )

        assert updated.filled_size == 30.0
        assert updated.remaining_size == 70.0
        assert updated.status == OrderStatus.PARTIALLY_FILLED

        # Complete the fill
        updated = await order_manager.process_fill(
            order_id=order_id,
            fill_size=70.0,
            fill_price=0.52,
        )

        assert updated.filled_size == 100.0
        assert updated.remaining_size == 0.0
        assert updated.status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_get_active_orders(self, order_manager):
        """Test getting active orders."""
        await order_manager.submit_order(
            market_id="0x123",
            outcome="Yes",
            side="BUY",
            size=100.0,
            price=0.5,
        )
        await order_manager.submit_order(
            market_id="0x456",
            outcome="No",
            side="SELL",
            size=50.0,
            price=0.6,
        )

        active = await order_manager.get_active_orders()
        assert len(active) == 2

    @pytest.mark.asyncio
    async def test_callbacks(self, order_manager):
        """Test event callbacks."""
        fill_events = []
        status_events = []
        complete_events = []

        order_manager.on_fill(lambda o, f: fill_events.append((o, f)))
        order_manager.on_status_change(lambda o: status_events.append(o))
        order_manager.on_complete(lambda o: complete_events.append(o))

        # Submit order
        order = await order_manager.submit_order(
            market_id="0x123",
            outcome="Yes",
            side="BUY",
            size=100.0,
            price=0.5,
        )

        # Should have status change callback
        assert len(status_events) >= 1

        # Process fill to completion
        order_id = order.order_id or order.client_order_id
        await order_manager.process_fill(
            order_id=order_id,
            fill_size=100.0,
            fill_price=0.5,
        )

        # Should have fill and complete callbacks
        assert len(fill_events) == 1
        assert len(complete_events) == 1


class TestFill:
    """Tests for Fill model."""

    def test_fill_value(self):
        """Test fill value calculation."""
        fill = Fill(
            fill_id="fill1",
            order_id="order1",
            size=50.0,
            price=0.6,
            fee=0.01,
        )

        assert fill.value == pytest.approx(30.0)  # 50 * 0.6
