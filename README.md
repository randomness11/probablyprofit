# [±] ProbablyProfit

<div align="center">

### AI-Powered Trading Framework for Prediction Markets

[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-3776ab?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/Tests-351%20Passing-brightgreen?style=for-the-badge)](https://github.com/randomness11/probablyprofit)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://github.com/randomness11/probablyprofit)

**Build autonomous trading bots for [Polymarket](https://polymarket.com) and [Kalshi](https://kalshi.com) using natural language strategies.**

[Quick Start](#quick-start) · [Documentation](#documentation) · [Examples](#strategy-examples) · [API Reference](#python-api) · [Contributing](#contributing)

</div>

---

## Overview

ProbablyProfit is a framework for building AI-powered trading bots that operate on prediction markets. Define your trading strategy in plain English, and let AI handle market analysis, position sizing, and trade execution.

```
You are a value investor for prediction markets.

Buy YES when your estimated probability is 20%+ higher than market price.
Buy NO when market is 20%+ overpriced. Size bets using Kelly criterion.
Never risk more than 5% per trade. Exit at 2x or cut losses at -30%.

Avoid: markets under $5k volume, ambiguous resolution criteria, coin flips.
```

**That's your entire trading strategy.** The framework handles the rest.

---

## Key Features

| Feature | Description |
|---------|-------------|
| **Natural Language Strategies** | Define trading logic in plain English—no coding required |
| **Multi-Provider AI** | Support for Claude, GPT-4, and Gemini with ensemble consensus mode |
| **Dual Platform Support** | Trade on Polymarket (crypto/global) and Kalshi (regulated/US) |
| **Risk Management** | Kelly criterion sizing, position limits, stop-loss, drawdown protection |
| **Order Management** | Full order lifecycle with partial fills, callbacks, and reconciliation |
| **Paper Trading** | Test strategies with simulated capital before going live |
| **Backtesting** | Validate strategies against historical data |
| **Real-time Data** | WebSocket feeds for live price updates |
| **Web Dashboard** | Monitor positions and P&L through a browser interface |
| **Extensible** | Plugin system for custom integrations and strategies |

---

## Quick Start

### Installation

```bash
# Install with pip
pip install probablyprofit[full]

# Or clone and install from source
git clone https://github.com/randomness11/probablyprofit.git
cd probablyprofit
pip install -e ".[full]"
```

### Configuration

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env with your credentials:
# - ANTHROPIC_API_KEY (or OPENAI_API_KEY, GOOGLE_API_KEY)
# - PRIVATE_KEY (Polymarket wallet) or KALSHI_API_KEY
```

### Run Your First Bot

```bash
# 1. Start with paper trading (simulated money)
probablyprofit run "Buy YES under 0.30 on high-volume markets" --paper

# 2. Or use a strategy file
probablyprofit run -s my_strategy.txt --paper

# 3. When ready, go live
probablyprofit run -s my_strategy.txt --live
```

### Docker Deployment

```bash
# Paper trading mode
docker compose --profile paper up -d

# Live trading mode (use with caution)
docker compose --profile live up -d

# View logs
docker compose logs -f
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        YOUR STRATEGY                             │
│            "Buy undervalued YES on high-volume markets"          │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                      AI DECISION ENGINE                          │
│                                                                  │
│    ┌──────────┐     ┌──────────┐     ┌──────────┐              │
│    │  Claude  │     │  GPT-4   │     │  Gemini  │              │
│    └──────────┘     └──────────┘     └──────────┘              │
│                            │                                     │
│              ┌─────────────┴─────────────┐                      │
│              │   Ensemble Mode: 2/3 Vote  │                      │
│              └────────────────────────────┘                      │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                      RISK MANAGEMENT                             │
│                                                                  │
│   Kelly Sizing  │  Position Limits  │  Stop-Loss  │  Drawdown   │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                      ORDER MANAGEMENT                            │
│                                                                  │
│   Order Lifecycle  │  Fill Tracking  │  Callbacks  │  Reconcile │
└─────────────────────────────────────────────────────────────────┘
                                 │
                 ┌───────────────┴───────────────┐
                 ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│       POLYMARKET        │     │         KALSHI          │
│    Crypto · Global      │     │    Regulated · US       │
│    USDC Settlement      │     │    USD Settlement       │
└─────────────────────────┘     └─────────────────────────┘
```

---

## Strategy Examples

### Value Investing Strategy

```
You are a value investor for prediction markets.

EDGE: Markets are inefficient. Crowds overreact to news and underreact
to base rates.

BUY YES when:
- Estimated probability is 20%+ higher than market price
- Resolution criteria is unambiguous
- Volume > $10,000
- Time to resolution > 7 days

BUY NO when:
- Market is 20%+ overpriced vs your estimate
- Same liquidity/clarity requirements

SIZING:
- Base: $20 per trade
- High conviction (30%+ edge): $50
- Max 5 concurrent positions

EXIT:
- Take profit at 2x
- Stop loss at -30%
- Close 24h before resolution

AVOID:
- Markets you don't understand
- Prices between 0.40-0.60
- Celebrity/meme markets
```

<details>
<summary><b>Arbitrage Strategy</b></summary>

```
Find price discrepancies between related markets.

If "Trump wins" is 0.45 and "Biden wins" is 0.58, the sum exceeds 1.00.
Trade the gap. Look for correlated markets with inconsistent pricing.
```
</details>

<details>
<summary><b>News Trading Strategy</b></summary>

```
You have access to recent news. Find information markets haven't priced in.

When you identify significant news affecting an outcome:
- Verify the source reliability
- Estimate the probability shift
- Enter position within 5 minutes
- Size based on edge magnitude
```
</details>

<details>
<summary><b>Mean Reversion Strategy</b></summary>

```
When markets move 20%+ in a day on no substantive news, fade the move.
Crowds overreact. Reversion is your edge.

Wait for the spike. Enter against it. Exit when price normalizes.
```
</details>

---

## Python API

For programmatic control:

```python
import asyncio
from probablyprofit import (
    PolymarketClient,
    AnthropicAgent,
    RiskManager,
    RiskLimits,
    OrderManager
)

async def main():
    # Initialize client
    client = PolymarketClient(private_key="0x...")

    # Configure risk management
    risk = RiskManager(
        initial_capital=1000.0,
        limits=RiskLimits(
            max_position_size=50.0,
            max_total_exposure=500.0,
            max_daily_loss=100.0
        )
    )

    # Set up order management
    orders = OrderManager(client=client)
    orders.on_fill = lambda o, f: print(f"Filled: {f.size} @ {f.price}")
    orders.on_complete = lambda o: print(f"Order complete: {o.order_id}")

    # Create AI agent with strategy
    agent = AnthropicAgent(
        client=client,
        risk_manager=risk,
        order_manager=orders,
        strategy_prompt=open("strategy.txt").read()
    )

    # Run trading loop
    await agent.run_loop()

asyncio.run(main())
```

---

## CLI Reference

```bash
# Trading
probablyprofit run "strategy" --paper       # Paper trading (simulated)
probablyprofit run -s file.txt --live       # Live trading (real money)
probablyprofit run --dry-run "strategy"     # Analysis only (no trades)

# Market Data
probablyprofit markets                      # List active markets
probablyprofit markets -q "bitcoin"         # Search markets
probablyprofit market <id>                  # Market details

# Portfolio
probablyprofit balance                      # Wallet balance
probablyprofit positions                    # Open positions
probablyprofit orders                       # Active orders
probablyprofit history                      # Trade history

# Tools
probablyprofit setup                        # Interactive configuration
probablyprofit backtest -s strategy.txt     # Backtest a strategy
probablyprofit dashboard                    # Launch web UI
```

---

## Configuration

### Environment Variables

```bash
# AI Provider (at least one required)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...

# Polymarket (for Polymarket trading)
PRIVATE_KEY=0x...

# Kalshi (for Kalshi trading)
KALSHI_API_KEY_ID=...
KALSHI_PRIVATE_KEY_PATH=/path/to/key.pem
```

### Config File

```yaml
# config.yaml
agent:
  default_model: claude-sonnet-4-20250514
  loop_interval: 300

risk:
  initial_capital: 1000.0
  max_position_size: 50.0
  max_total_exposure: 0.5
  stop_loss_pct: 0.20

platforms:
  polymarket:
    enabled: true
  kalshi:
    enabled: false
```

See [.env.example](.env.example) for all configuration options.

---

## Supported Platforms

| Platform | Type | Region | Settlement | Authentication |
|----------|------|--------|------------|----------------|
| [Polymarket](https://polymarket.com) | Crypto | Global | USDC on Polygon | Ethereum wallet |
| [Kalshi](https://kalshi.com) | Regulated | US | USD | RSA key pair |

---

## Documentation

- [Getting Started Guide](GETTING_STARTED.md)
- [Kalshi Integration Guide](KALSHI_GUIDE.md)
- [Deployment Guide](DEPLOY.md)
- [API Reference](docs/API_REFERENCE.md)
- [Strategy Writing Guide](docs/PROMPT_ENGINEERING.md)
- [Architecture Overview](probablyprofit/ARCHITECTURE.md)

---

## Risk Disclaimer

**This is experimental software for educational and research purposes.**

- **No guarantees**: This software is provided "as-is" without warranty
- **AI limitations**: Language models make mistakes and may execute poor trades
- **Financial risk**: Trading involves risk of loss, including total loss of capital
- **Your responsibility**: You are solely responsible for your trading decisions
- **Not financial advice**: The authors are not financial advisors

**Always start with paper trading. Never risk money you cannot afford to lose.**

---

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](probablyprofit/CONTRIBUTING.md) for guidelines.

Areas of interest:
- Exchange integrations
- Strategy templates
- Risk management improvements
- Documentation

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

**Built by [@ankitkr0](https://twitter.com/ankitkr0)**

[GitHub](https://github.com/randomness11/probablyprofit) · [Twitter](https://twitter.com/ankitkr0)

</div>
