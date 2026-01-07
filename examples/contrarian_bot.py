"""
Contrarian Bot Example

Fades extreme price movements and bets against the crowd.
"""

import asyncio
import os
from dotenv import load_dotenv

from poly16z import PolymarketClient, AnthropicAgent, RiskManager
from poly16z.utils import setup_logging

# Load environment variables
load_dotenv()

# Strategy prompt for the AI agent
CONTRARIAN_STRATEGY = """
You are a contrarian trading bot for Polymarket prediction markets.

Your strategy:
1. Identify markets with extreme prices (>85% or <15%)
2. Look for markets where the crowd may be overreacting
3. Take positions against the prevailing sentiment
4. Target mean reversion opportunities

Entry rules:
- Enter when price is >90% or <10% (extreme overconfidence)
- Market should have decent liquidity (>$500)
- Look for catalysts that might cause reversion
- Position size: 3-5% of capital

Exit rules:
- Take profit when price moves back toward 50% (mean)
- Target 30-50% profit on the trade
- Stop loss if price moves further to extreme (additional 5%)
- Exit if new information confirms the extreme price is justified

Risk management:
- Smaller position sizes (3% per trade) due to contrarian nature
- Maximum 2 open positions at once
- Be patient - mean reversion can take time
- Never fight a strong trend for too long

When analyzing markets, consider:
- Is the extreme price justified by fundamentals?
- Is there emotional/reactionary trading happening?
- What's the timeline to resolution?
- Is there a catalyst for reversion?

Contrarian trading is riskier, so be selective and patient.

Always respond with a JSON decision object.
"""


async def main():
    """Run the contrarian bot."""
    # Setup logging
    setup_logging(level="INFO")

    # Initialize Polymarket client
    client = PolymarketClient(
        api_key=os.getenv("POLYMARKET_API_KEY"),
        secret=os.getenv("POLYMARKET_SECRET"),
        passphrase=os.getenv("POLYMARKET_PASSPHRASE"),
    )

    # Initialize risk manager with conservative limits
    risk_manager = RiskManager(
        initial_capital=float(os.getenv("MAX_TOTAL_EXPOSURE", "1000")),
    )
    risk_manager.limits.max_position_size = 50.0  # Smaller positions
    risk_manager.limits.max_positions = 2  # Fewer concurrent positions

    # Initialize AI agent
    agent = AnthropicAgent(
        client=client,
        risk_manager=risk_manager,
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        strategy_prompt=CONTRARIAN_STRATEGY,
        name="ContrarianBot",
        loop_interval=600,  # Check every 10 minutes
        temperature=0.7,  # Slightly lower temperature for more conservative decisions
    )

    # Run the agent
    print("🚀 Starting Contrarian Bot...")
    print("📊 Strategy: Contrarian/Mean Reversion")
    print("⏱️  Loop interval: 10 minutes")
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
