"""
News-Driven Bot Example

Trades based on breaking news and events.
"""

import asyncio
import os

from dotenv import load_dotenv
from probablyprofit import AnthropicAgent, PolymarketClient, RiskManager
from probablyprofit.data import NewsCollector
from probablyprofit.utils import setup_logging

# Load environment variables
load_dotenv()

# Strategy prompt for the AI agent
NEWS_STRATEGY = """
You are a news-driven trading bot for Polymarket prediction markets.

Your strategy:
1. Monitor breaking news and major events
2. Identify markets that will be affected by the news
3. Trade quickly before the market fully adjusts
4. Look for markets where news creates mispricings

Entry rules:
- Enter when significant news breaks that affects a market
- News should be from credible sources
- Market should not have fully priced in the news yet
- Position size: 5-8% of capital for high-confidence news plays
- Move quickly but verify the news is legitimate

Exit rules:
- Take profit once market adjusts to news (usually 20-40% gain)
- Exit if news is contradicted or turns out to be false
- Hold if news impact is sustained and ongoing
- Stop loss at 20% if you misread the news impact

Risk management:
- Verify news from multiple sources before trading
- Be aware of "fake news" and misinformation
- Larger positions for major, verified news
- Smaller positions for developing/unconfirmed stories
- Maximum 4 open positions

When analyzing markets and news:
- How reliable is the news source?
- How directly does this impact the market outcome?
- Has the market already priced this in?
- Is there a time advantage (are you early)?
- What's the expected magnitude of impact?

Speed matters, but accuracy matters more.

Always respond with a JSON decision object.
"""


class NewsBot(AnthropicAgent):
    """Custom agent that incorporates news data."""

    def __init__(self, *args, news_collector: NewsCollector, **kwargs):
        super().__init__(*args, **kwargs)
        self.news_collector = news_collector

    async def observe(self):
        """Enhanced observation that includes news."""
        # Get base observation
        observation = await super().observe()

        # Collect recent news
        news = await self.news_collector.collect(hours=2)

        # Add news to observation signals
        observation.signals["news"] = [
            {
                "title": article.title,
                "source": article.source,
                "published": article.published.isoformat(),
                "summary": article.summary,
            }
            for article in news[:10]  # Top 10 most recent
        ]

        return observation


async def main():
    """Run the news-driven bot."""
    # Setup logging
    setup_logging(level="INFO")

    # Initialize Polymarket client
    client = PolymarketClient(
        api_key=os.getenv("POLYMARKET_API_KEY"),
        secret=os.getenv("POLYMARKET_SECRET"),
        passphrase=os.getenv("POLYMARKET_PASSPHRASE"),
    )

    # Initialize news collector
    news_collector = NewsCollector(
        news_api_key=os.getenv("NEWS_API_KEY"),
    )

    # Initialize risk manager
    risk_manager = RiskManager(
        initial_capital=float(os.getenv("MAX_TOTAL_EXPOSURE", "1000")),
    )
    risk_manager.limits.max_positions = 4

    # Initialize AI agent with news integration
    agent = NewsBot(
        client=client,
        risk_manager=risk_manager,
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        strategy_prompt=NEWS_STRATEGY,
        news_collector=news_collector,
        name="NewsBot",
        loop_interval=180,  # Check every 3 minutes for news
    )

    # Run the agent
    print("🚀 Starting News-Driven Bot...")
    print("📊 Strategy: News-driven trading")
    print("⏱️  Loop interval: 3 minutes")
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
