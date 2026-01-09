#!/usr/bin/env python3
"""
Poly16z Interactive CLI

Commands to inspect markets, check balance, and test trades.
"""

import asyncio
import os
import sys
import argparse

# Add grandparent directory to path so 'probablyprofit' folder is importable
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from dotenv import load_dotenv
from loguru import logger

from probablyprofit.api.client import PolymarketClient


async def cmd_get_markets(args):
    """Fetch and display active markets."""
    client = PolymarketClient()
    
    try:
        markets = await client.get_markets(active=True, limit=args.limit)
        
        if not markets:
            print("No markets found.")
            return
            
        print(f"\n📊 Top {len(markets)} Active Markets (by volume):\n")
        print("-" * 80)
        
        for i, m in enumerate(markets, 1):
            price_str = f"Yes: {m.outcome_prices[0]:.2f} / No: {m.outcome_prices[1]:.2f}" if len(m.outcome_prices) >= 2 else "N/A"
            print(f"{i}. {m.question[:60]}...")
            print(f"   ID: {m.condition_id[:20]}... | Volume: ${m.volume:,.0f} | {price_str}")
            print()
            
    finally:
        await client.close()


async def cmd_check_balance(args):
    """Check USDC balance."""
    load_dotenv()
    
    client = PolymarketClient(
        api_key=os.getenv("POLYMARKET_API_KEY"),
        secret=os.getenv("POLYMARKET_API_SECRET"),
        passphrase=os.getenv("POLYMARKET_API_PASSPHRASE")
    )
    
    try:
        balance = await client.get_balance()
        print(f"\n💰 Balance: ${balance:,.2f} USDC\n")
    finally:
        await client.close()


async def cmd_get_positions(args):
    """Get current positions."""
    load_dotenv()
    
    client = PolymarketClient(
        api_key=os.getenv("POLYMARKET_API_KEY"),
        secret=os.getenv("POLYMARKET_API_SECRET"),
        passphrase=os.getenv("POLYMARKET_API_PASSPHRASE")
    )
    
    try:
        positions = await client.get_positions()
        
        if not positions:
            print("\n📭 No open positions.\n")
            return
            
        print(f"\n📈 Open Positions ({len(positions)}):\n")
        for p in positions:
            print(f"  - Market: {p.market_id[:20]}...")
            print(f"    Outcome: {p.outcome} | Size: {p.size} | Avg Entry: {p.avg_entry_price:.2f}")
            print()
    finally:
        await client.close()


def main():
    parser = argparse.ArgumentParser(
        description="Poly16z CLI - Interact with Polymarket",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/cli.py get-markets --limit 10
  python scripts/cli.py check-balance
  python scripts/cli.py get-positions
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # get-markets
    p_markets = subparsers.add_parser("get-markets", help="List active markets")
    p_markets.add_argument("--limit", type=int, default=10, help="Number of markets to fetch")
    p_markets.set_defaults(func=cmd_get_markets)
    
    # check-balance
    p_balance = subparsers.add_parser("check-balance", help="Check USDC balance")
    p_balance.set_defaults(func=cmd_check_balance)
    
    # get-positions
    p_positions = subparsers.add_parser("get-positions", help="Show open positions")
    p_positions.set_defaults(func=cmd_get_positions)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Run the async command
    asyncio.run(args.func(args))


if __name__ == "__main__":
    main()
