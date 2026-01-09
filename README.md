# ProbablyProfit 👀

<div align="center">

**AI-Powered Trading Bots for Polymarket & Kalshi**

*probably nothing*

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![WAGMI](https://img.shields.io/badge/WAGMI-🚀-green.svg)]()

Build intelligent trading bots for Polymarket & Kalshi in minutes using natural language strategy prompts and AI (Claude, Gemini, or GPT-4).

Write your strategy in plain English. Let AI do the rest. Probably profit.

[Quick Start](#-quick-start) • [Examples](#-example-strategies) • [Documentation](#-documentation) • [Create Your Own](#-create-your-own-bot-in-10-minutes)

</div>

---

A powerful, modular Python framework for creating intelligent trading bots on prediction markets (Polymarket & Kalshi) using AI. Define your strategy in natural language, and let Claude, Gemini, or GPT-4 handle the decision-making.

Few understand. 🧠

## ✨ Features

- **🤖 Multi-Provider AI** - Choose Claude, Gemini, or GPT-4 for decision-making based on natural language strategy prompts
- **📊 Multi-Platform Support** - Works with Polymarket & Kalshi (more coming soon)
- **🛡️ Built-in Risk Management** - Position sizing, stop-loss, take-profit, and exposure limits (don't get rekt)
- **📰 Multi-Source Data Ingestion** - News APIs, RSS feeds, Twitter, and market signals
- **📈 Backtesting & Simulation** - Test strategies on historical data before risking real capital (highly recommended)
- **🔌 Modular Architecture** - Use components independently or build custom solutions
- **⚡ Async by Default** - High-performance async/await for real-time trading
- **📝 Type-Safe** - Fully typed with Pydantic models
- **🎯 Natural Language Strategies** - Write your strategy in plain English, no PhD required

### 🤖 Supported AI Providers

Choose your preferred AI model:

| Provider | Agent Class | Model | Best For |
|----------|------------|-------|----------|
| **Anthropic** | `AnthropicAgent` | Claude Sonnet 4.5 | Advanced reasoning, long context |
| **Google** | `GeminiAgent` | Gemini 2.0 Flash | Fast responses, cost-effective |
| **OpenAI** | `OpenAIAgent` | GPT-4o | Well-rounded performance |

All agents share the same interface - just swap the class!

```python
from probablyprofit import AnthropicAgent, GeminiAgent, OpenAIAgent

# Use Claude
agent = AnthropicAgent(client, risk_manager, anthropic_api_key, STRATEGY)

# Or use Gemini
agent = GeminiAgent(client, risk_manager, google_api_key, STRATEGY)

# Or use GPT-4
agent = OpenAIAgent(client, risk_manager, openai_api_key, STRATEGY)
```

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/probablyprofit.git
cd probablyprofit

# Install dependencies
pip install -r requirements.txt

# Copy example environment file
cp .env.example .env
```

### Configuration

Edit `.env` with your credentials:

```bash
# Polymarket API (get from https://polymarket.com)
POLYMARKET_API_KEY=your_api_key
POLYMARKET_SECRET=your_secret
POLYMARKET_PASSPHRASE=your_passphrase

# Wallet
PRIVATE_KEY=your_ethereum_private_key

# Anthropic API (get from https://console.anthropic.com)
ANTHROPIC_API_KEY=your_anthropic_key

# Optional: News & Social APIs
NEWS_API_KEY=your_newsapi_key
TWITTER_BEARER_TOKEN=your_twitter_token

# Bot Settings
TRADING_MODE=paper  # or 'live'
MAX_TOTAL_EXPOSURE=1000
```

### Run Your First Bot

```bash
# Run the momentum trading bot
python examples/momentum_bot.py
```

That's it! Your bot is now running and will:
1. Monitor Polymarket markets every 5 minutes
2. Detect momentum signals (>10% price movements)
3. Make AI-powered trading decisions
4. Execute trades within your risk limits

## 📚 Example Strategies

### 1. Momentum Bot

Trades markets with strong price momentum:

```bash
python examples/momentum_bot.py
```

**Strategy**: Identifies markets with >10% price changes and trades in the direction of momentum.

### 2. Contrarian Bot

Fades extreme movements and bets against the crowd:

```bash
python examples/contrarian_bot.py
```

**Strategy**: Takes positions against markets with extreme prices (>90% or <10%), betting on mean reversion.

### 3. News-Driven Bot

Trades based on breaking news:

```bash
python examples/news_bot.py
```

**Strategy**: Monitors news feeds and trades markets before they fully adjust to new information.

## 🎯 Create Your Own Bot in 10 Minutes

### Step 1: Define Your Strategy in Natural Language

```python
MY_STRATEGY = """
You are a value trader for Polymarket.

Your strategy:
1. Look for markets where the price doesn't match fundamentals
2. Check prediction quality and liquidity
3. Take contrarian positions on mispriced markets

Entry rules:
- Market price should differ >15% from your analysis
- Minimum $1000 liquidity
- Use 10% of capital per trade

Exit rules:
- Take profit at 30% gain
- Stop loss at 20% loss
"""
```

### Step 2: Create Your Bot

```python
import asyncio
import os
from dotenv import load_dotenv
from probablyprofit import PolymarketClient, AnthropicAgent, RiskManager

load_dotenv()

async def main():
    # Initialize components
    client = PolymarketClient(
        api_key=os.getenv("POLYMARKET_API_KEY"),
        secret=os.getenv("POLYMARKET_SECRET"),
        passphrase=os.getenv("POLYMARKET_PASSPHRASE"),
    )

    risk_manager = RiskManager(initial_capital=1000.0)

    # Create AI agent with your strategy
    agent = AnthropicAgent(
        client=client,
        risk_manager=risk_manager,
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        strategy_prompt=MY_STRATEGY,
        loop_interval=300,  # Check every 5 minutes
    )

    # Run!
    await agent.run()

if __name__ == "__main__":
    asyncio.run(main())
```

### Step 3: Run It!

```bash
python my_bot.py
```

**That's it!** Your custom AI trading bot is now running.

## 🏗️ Architecture

The framework is built on a modular architecture:

```
probablyprofit/
├── api/           # Polymarket API client
├── agent/         # AI agent framework (observe-decide-act)
├── risk/          # Risk management primitives
├── data/          # News, social, and signal collectors
├── backtesting/   # Backtesting and simulation engine
└── utils/         # Logging and utilities
```

### Core Components

**PolymarketClient** - API wrapper for markets, orders, positions
```python
async with PolymarketClient(api_key=key) as client:
    markets = await client.get_markets()
    order = await client.place_order(
        market_id="...",
        outcome="Yes",
        side="BUY",
        size=10,
        price=0.60
    )
```

**AnthropicAgent** - AI-powered trading agent
```python
agent = AnthropicAgent(
    client=client,
    risk_manager=risk_manager,
    anthropic_api_key=key,
    strategy_prompt=STRATEGY,
)
await agent.run()
```

**RiskManager** - Position sizing and risk controls
```python
risk_manager = RiskManager(initial_capital=1000.0)
risk_manager.limits.max_position_size = 100.0
risk_manager.limits.max_positions = 5

# Check if trade is allowed
if risk_manager.can_open_position(size=10, price=0.60):
    # Place trade
    pass
```

**SignalGenerator** - Technical signals from market data
```python
from probablyprofit.data import SignalGenerator

signal_gen = SignalGenerator()
signals = signal_gen.generate_signals(markets)

for signal in signals:
    if signal.type == "momentum" and signal.strength > 0.7:
        print(f"Strong momentum: {signal.direction}")
```

## 🧪 Backtesting

Test your strategy before risking real money:

```python
from probablyprofit.backtesting import BacktestEngine

# Create backtest engine
backtest = BacktestEngine(initial_capital=1000.0)

# Run backtest
result = await backtest.run_backtest(
    agent=my_agent,
    market_data=historical_markets,
    timestamps=timestamps,
)

# Analyze results
print(f"Total Return: {result.total_return_pct:.2%}")
print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
print(f"Win Rate: {result.win_rate:.1%}")
print(f"Max Drawdown: {result.max_drawdown:.1%}")
```

## 📖 Documentation

### API Reference

#### PolymarketClient

```python
class PolymarketClient:
    async def get_markets(
        active: bool = True,
        limit: int = 100
    ) -> List[Market]

    async def get_market(
        condition_id: str
    ) -> Optional[Market]

    async def place_order(
        market_id: str,
        outcome: str,
        side: str,  # "BUY" or "SELL"
        size: float,
        price: float
    ) -> Optional[Order]

    async def get_positions() -> List[Position]

    async def get_balance() -> float
```

#### BaseAgent

```python
class BaseAgent(ABC):
    async def observe() -> Observation

    @abstractmethod
    async def decide(
        observation: Observation
    ) -> Decision

    async def act(decision: Decision) -> bool

    async def run_loop() -> None
```

#### RiskManager

```python
class RiskManager:
    def can_open_position(
        size: float,
        price: float
    ) -> bool

    def calculate_position_size(
        price: float,
        confidence: float,
        method: str = "fixed_pct"
    ) -> float

    def should_stop_loss(
        entry_price: float,
        current_price: float,
        size: float
    ) -> bool
```

### Best Practices

#### 1. Strategy Prompt Engineering

**Good prompts are**:
- Specific about entry/exit rules
- Include risk management guidelines
- Specify position sizing
- Define what to look for in markets

**Example**:
```python
GOOD_PROMPT = """
You are a momentum trader.

Entry: Price moved >10%, volume >$1000, liquidity >$500
Exit: +25% profit OR -15% loss
Position size: 5% of capital
Max positions: 3
"""

BAD_PROMPT = """
Trade momentum.
"""
```

#### 2. Risk Management

Always set appropriate limits:

```python
risk_manager.limits.max_position_size = 100.0  # Max $100 per position
risk_manager.limits.max_total_exposure = 500.0  # Max $500 total
risk_manager.limits.max_positions = 5  # Max 5 positions
risk_manager.limits.max_daily_loss = 100.0  # Stop if lose $100/day
```

#### 3. Start with Paper Trading

Test thoroughly before using real money:

```python
# In .env
TRADING_MODE=paper

# Or in code
client = PolymarketClient(
    api_key=key,
    testnet=True  # Use testnet
)
```

#### 4. Monitor and Log

Enable detailed logging:

```python
from probablyprofit.utils import setup_logging

setup_logging(
    level="INFO",
    log_file="bot.log"
)
```

#### 5. Backtest First

Always backtest before live trading:

```python
# Test on historical data
backtest_result = await backtest.run_backtest(
    agent=my_agent,
    market_data=historical_data,
    timestamps=timestamps
)

# Only go live if metrics are good
if backtest_result.sharpe_ratio > 1.0:
    await agent.run()  # Go live
```

## 🔧 Advanced Usage

### Custom Agents

Create custom agents by extending `BaseAgent`:

```python
from probablyprofit.agent.base import BaseAgent, Observation, Decision

class MyCustomAgent(BaseAgent):
    async def decide(self, observation: Observation) -> Decision:
        # Your custom decision logic here
        for market in observation.markets:
            if market.volume > 10000:
                return Decision(
                    action="buy",
                    market_id=market.condition_id,
                    outcome=market.outcomes[0],
                    size=10.0,
                    price=0.50,
                    reasoning="High volume market"
                )

        return Decision(action="hold")
```

### Custom Data Sources

Add your own data sources:

```python
from probablyprofit.data.news import NewsCollector

class MyDataCollector:
    async def collect_data(self):
        # Fetch from your API
        data = await fetch_my_data()
        return data

# Integrate with agent
class MyAgent(BaseAgent):
    def __init__(self, *args, data_collector, **kwargs):
        super().__init__(*args, **kwargs)
        self.data_collector = data_collector

    async def observe(self):
        observation = await super().observe()
        custom_data = await self.data_collector.collect_data()
        observation.signals["custom"] = custom_data
        return observation
```

### Custom Risk Rules

Extend risk manager:

```python
from probablyprofit.risk import RiskManager

class MyRiskManager(RiskManager):
    def can_open_position(self, size, price, market_id=None):
        # Call parent checks
        if not super().can_open_position(size, price, market_id):
            return False

        # Add custom checks
        if self.current_exposure > 0.5 * self.initial_capital:
            logger.warning("Already at 50% exposure")
            return False

        return True
```

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## ⚠️ Disclaimer

**This software is for educational purposes only. Not financial advice. Probably nothing.**

- Trading involves risk of loss (you could get rekt)
- Past performance doesn't guarantee future results (ser, seriously)
- Only trade with money you can afford to lose (don't be that guy)
- The authors are not responsible for any losses (DYOR)
- This is experimental software - use at your own risk
- Always do your own research (probably should've mentioned this first)

## 📄 License

MIT License - see LICENSE file for details

## 🙏 Acknowledgments

- Built with [Anthropic Claude](https://anthropic.com), OpenAI, and Google Gemini
- Polymarket & Kalshi API integrations
- Inspired by the prediction market & crypto degen community
- Shoutout to everyone who said "few understand" unironically

## 📞 Support

- 📖 Documentation: [Coming soon]
- 🐛 Issues: [GitHub Issues](https://github.com/randomness11/probablyprofit/issues)
- 💬 Discussions: [GitHub Discussions](https://github.com/randomness11/probablyprofit/discussions)
- 🐦 Twitter: Drop a reply if you're building with this

---

**Probably profit. 🚀**

Made with ❤️ by degens, for degens

*WAGMI*
