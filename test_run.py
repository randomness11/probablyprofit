#!/usr/bin/env python3
import asyncio
import os
import sys

# Suppress warnings
import warnings
warnings.filterwarnings("ignore")

from dotenv import load_dotenv
load_dotenv()

print("Loading modules...")
sys.stdout.flush()

from probablyprofit.api.client import PolymarketClient
from probablyprofit.agent.openai_agent import OpenAIAgent
from probablyprofit.risk.manager import RiskManager

STRATEGY = """
HIGH VOLUME trading bot. Find BEST opportunity:
1. High volume markets (safer)
2. Mispriced odds where you see 10%+ edge
3. YES < 20% or > 80% that seem WRONG

Be AGGRESSIVE. Recommend your best trade with reasoning.
"""

async def main():
    print("Initializing client...")
    sys.stdout.flush()

    client = PolymarketClient(private_key=os.getenv("PRIVATE_KEY"))
    risk = RiskManager(initial_capital=1000.0)

    print("Creating agent...")
    sys.stdout.flush()

    agent = OpenAIAgent(
        client=client,
        risk_manager=risk,
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        strategy_prompt=STRATEGY,
        model="gpt-4o",
        dry_run=True
    )

    print("Fetching markets...")
    sys.stdout.flush()

    observation = await agent.observe()
    print(f"Found {len(observation.markets)} markets")
    sys.stdout.flush()

    markets = sorted(observation.markets, key=lambda m: m.volume, reverse=True)[:10]
    print("\nTOP 10 BY VOLUME:")
    for i, m in enumerate(markets, 1):
        yes = m.outcome_prices[0] if m.outcome_prices else 0.5
        print(f"{i}. {m.question[:50]:50} YES:{yes:4.0%} Vol:${m.volume:,.0f}")
    sys.stdout.flush()

    print("\nAI analyzing...")
    sys.stdout.flush()

    decision = await agent.decide(observation)

    print(f"\n{'='*60}")
    print(f"DECISION: {decision.action.upper()}")
    if decision.market_id:
        for m in observation.markets:
            if m.condition_id == decision.market_id:
                print(f"Market: {m.question}")
                break
        print(f"Outcome: {decision.outcome}")
        print(f"Size: ${decision.size:.2f}")
        print(f"Confidence: {decision.confidence:.0%}")
    print(f"\nReasoning: {decision.reasoning}")
    print(f"{'='*60}")
    sys.stdout.flush()

    await client.close()

if __name__ == "__main__":
    asyncio.run(main())
