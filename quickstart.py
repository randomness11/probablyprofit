#!/usr/bin/env python3
"""
Quickstart Script

Run this to quickly test the framework with a simple bot.
"""

import asyncio
import os
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Check for required environment variables
required_vars = ["ANTHROPIC_API_KEY"]
missing_vars = [var for var in required_vars if not os.getenv(var)]

if missing_vars:
    print("❌ Missing required environment variables:")
    for var in missing_vars:
        print(f"   - {var}")
    print("\nPlease set them in your .env file")
    print("See .env.example for reference")
    exit(1)

# Import framework
from poly16z import PolymarketClient, AnthropicAgent, RiskManager
from poly16z.utils import setup_logging

# Simple test strategy
TEST_STRATEGY = """
You are a test trading bot for Polymarket.

For this demo, you should:
1. Observe the markets
2. Look for interesting opportunities
3. Explain your analysis
4. Return action: "hold" (since this is a test)

Your goal is to demonstrate that you can analyze markets intelligently,
but not actually place any trades (just return "hold" decisions).

Provide clear, analytical reasoning for what you observe.

Always respond with a JSON decision object with action: "hold".
"""


async def main():
    """Run quickstart demo."""
    print("=" * 60)
    print("🚀 Polymarket AI Bot Framework - Quickstart")
    print("=" * 60)
    print()

    # Setup logging
    setup_logging(level="INFO")

    print("📊 Initializing components...")
    print()

    # Initialize Polymarket client (read-only mode if no credentials)
    client = PolymarketClient(
        api_key=os.getenv("POLYMARKET_API_KEY"),
        secret=os.getenv("POLYMARKET_SECRET"),
        passphrase=os.getenv("POLYMARKET_PASSPHRASE"),
    )

    # Initialize risk manager
    risk_manager = RiskManager(initial_capital=1000.0)

    # Initialize AI agent
    agent = AnthropicAgent(
        client=client,
        risk_manager=risk_manager,
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        strategy_prompt=TEST_STRATEGY,
        name="QuickstartBot",
        loop_interval=60,
    )

    print("✅ Components initialized successfully!")
    print()
    print("📈 Running one iteration of the trading loop...")
    print("   (This will fetch markets and ask Claude for analysis)")
    print()

    try:
        # Run one iteration
        observation = await agent.observe()
        print(f"📊 Observed {len(observation.markets)} markets")
        print()

        if observation.markets:
            print("Top 3 markets:")
            for i, market in enumerate(observation.markets[:3], 1):
                print(f"{i}. {market.question}")
                print(f"   Volume: ${market.volume:,.0f} | Liquidity: ${market.liquidity:,.0f}")
            print()

        print("🤖 Asking Claude for analysis...")
        decision = await agent.decide(observation)

        print()
        print("=" * 60)
        print("📋 Claude's Decision:")
        print("=" * 60)
        print(f"Action: {decision.action}")
        print(f"Confidence: {decision.confidence:.0%}")
        print()
        print("Reasoning:")
        print(decision.reasoning)
        print()

        await client.close()

        print("=" * 60)
        print("✅ Quickstart completed successfully!")
        print("=" * 60)
        print()
        print("Next steps:")
        print("1. Check out the example bots in examples/")
        print("2. Read docs/PROMPT_ENGINEERING.md for strategy tips")
        print("3. Create your own bot with a custom strategy prompt")
        print()
        print("To run a full bot:")
        print("  python examples/momentum_bot.py")
        print()

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
