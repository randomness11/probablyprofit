import asyncio
import sys
import os

# Add parent directory to path to allow importing probablyprofit as a module
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from probablyprofit.api.client import PolymarketClient

async def main():
    print("Testing get_balance_no_creds...")
    client = PolymarketClient()
    balance = await client.get_balance()
    print(f"Balance: {balance}")
    assert balance == 0.0
    
    print("Testing get_positions_no_creds...")
    positions = await client.get_positions()
    print(f"Positions: {positions}")
    assert positions == []
    
    await client.close()
    print("SUCCESS: All tests passed!")

if __name__ == "__main__":
    asyncio.run(main())
