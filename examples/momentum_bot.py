"""
Momentum Bot Example

Trades markets with strong price momentum.
"""

import asyncio
import os

from dotenv import load_dotenv
from probablyprofit import AnthropicAgent, PolymarketClient, RiskManager
from probablyprofit.utils import setup_logging

# Load environment variables
load_dotenv()

# Strategy prompt for the AI agent
MOMENTUM_STRATEGY = """
You are a momentum trading bot for Polymarket prediction markets.

Your strategy:
1. Look for markets with strong recent price movements (>10% change)
2. Check that the market has good liquidity (>$1000)
3. Verify the market has substantial volume
4. Trade in the direction of the momentum

Entry rules:
- Only enter when price has moved >10% in a clear direction
- Market must have >$1000 liquidity
- Daily volume should be >$500
- Use 5% of available capital per trade

Exit rules:
- Take profit at 25% gain
- Stop loss at 15% loss
- Exit if momentum reverses (price moves >5% against position)

Risk management:
- Never risk more than 5% of capital on a single trade
- Maximum 3 open positions at once
- If you have 2 or more losing trades in a row, reduce position size by 50%

When analyzing markets, focus on:
- Recent price action and momentum strength
- Volume patterns and liquidity
- Time to market resolution
- Overall market structure

Always respond with a JSON decision object.
"""


async def main():
    """Run the momentum bot."""
    # Setup logging
    setup_logging(level="INFO")

    # Initialize Polymarket client
    client = PolymarketClient(
        api_key=os.getenv("POLYMARKET_API_KEY"),
        secret=os.getenv("POLYMARKET_SECRET"),
        passphrase=os.getenv("POLYMARKET_PASSPHRASE"),
    )

    # Initialize risk manager
    risk_manager = RiskManager(
        initial_capital=float(os.getenv("MAX_TOTAL_EXPOSURE", "1000")),
    )

    # Initialize AI agent
    agent = AnthropicAgent(
        client=client,
        risk_manager=risk_manager,
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        strategy_prompt=MOMENTUM_STRATEGY,
        name="MomentumBot",
        loop_interval=300,  # Check every 5 minutes
    )

    # Run the agent
    print("🚀 Starting Momentum Bot...")
    print("📊 Strategy: Momentum trading")
    print("⏱️  Loop interval: 5 minutes")
    print("💰 Max exposure: ${}".format(os.getenv("MAX_TOTAL_EXPOSURE", "1000")))
    print("\nPress Ctrl+C to stop\n")

    try:
        await agent.run()
    except KeyboardInterrupt:
        print("\n\n🛑 Stopping bot...")
        agent.stop()
        await client.close()

    # Print final stats
    print("\n📈 Final Statistics:")
    stats = risk_manager.get_stats()
    print(f"  Capital: ${stats['current_capital']:.2f}")
    print(f"  Total P&L: ${stats['total_pnl']:+.2f}")
    print(f"  Return: {stats['return_pct']:+.2%}")
    print(f"  Total Trades: {stats['total_trades']}")
    print(f"  Win Rate: {stats['win_rate']:.1%}")


if __name__ == "__main__":
    asyncio.run(main())
