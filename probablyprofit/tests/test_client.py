"""
Tests for the Polymarket API client.
"""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from probablyprofit.api.client import PolymarketClient, Market, Order, Position


@pytest.fixture
def client():
    """Create a mock client without real credentials."""
    return PolymarketClient(
        api_key="test_key",
        secret="test_secret",
        passphrase="test_passphrase"
    )


class TestMarketDataclass:
    def test_market_creation(self):
        market = Market(
            condition_id="0x123",
            question="Will it rain tomorrow?",
            end_date=datetime(2024, 12, 31),
            outcomes=["Yes", "No"],
            outcome_prices=[0.65, 0.35],
            volume=10000.0,
            liquidity=5000.0
        )
        assert market.condition_id == "0x123"
        assert market.question == "Will it rain tomorrow?"
        assert market.outcomes == ["Yes", "No"]
        assert market.active is True


class TestOrderDataclass:
    def test_order_creation(self):
        order = Order(
            market_id="0x123",
            outcome="Yes",
            side="BUY",
            size=100.0,
            price=0.5
        )
        assert order.market_id == "0x123"
        assert order.status == "pending"
        assert order.filled_size == 0.0


class TestPositionDataclass:
    def test_position_value(self):
        position = Position(
            market_id="0x123",
            outcome="Yes",
            size=100.0,
            avg_price=0.5,
            current_price=0.7
        )
        assert position.value == 70.0  # 100 * 0.7
        assert position.unrealized_pnl == 20.0  # (0.7 - 0.5) * 100


class TestPolymarketClient:
    @pytest.mark.asyncio
    async def test_get_balance_returns_float(self, client):
        """Test that get_balance returns a float."""
        with patch.object(client, '_http', new_callable=AsyncMock) as mock_http:
            mock_response = MagicMock()
            mock_response.json.return_value = {"balance": "1000.50"}
            mock_http.get.return_value = mock_response
            
            # Note: actual implementation may differ
            # This tests the expected interface
            balance = await client.get_balance()
            assert isinstance(balance, float)

    @pytest.mark.asyncio
    async def test_close_client(self, client):
        """Test that close doesn't raise."""
        await client.close()  # Should not raise


class TestValidation:
    def test_price_validation(self):
        """Prices must be between 0 and 1."""
        from probablyprofit.utils.validators import validate_price
        
        assert validate_price(0.5) == 0.5
        
        with pytest.raises(ValueError):
            validate_price(1.5)
        
        with pytest.raises(ValueError):
            validate_price(-0.1)

    def test_side_validation(self):
        """Side must be BUY or SELL."""
        from probablyprofit.utils.validators import validate_side
        
        assert validate_side("BUY") == "BUY"
        assert validate_side("SELL") == "SELL"
        
        with pytest.raises(ValueError):
            validate_side("HOLD")
