import pytest
import os
from probablyprofit.api.client import PolymarketClient

@pytest.mark.asyncio
async def test_get_balance_no_creds():
    """Test get_balance returns 0.0 comfortably without credentials."""
    client = PolymarketClient()
    balance = await client.get_balance()
    assert balance == 0.0
    await client.close()

@pytest.mark.asyncio
async def test_get_positions_no_creds():
    """Test get_positions returns empty list without credentials."""
    client = PolymarketClient()
    positions = await client.get_positions()
    assert positions == []
    await client.close()
