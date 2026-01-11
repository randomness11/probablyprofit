# ProbablyProfit

<div align="center">

**AI-Powered Prediction Market Trading Bots**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PyPI](https://img.shields.io/pypi/v/probablyprofit.svg)](https://pypi.org/project/probablyprofit/)

Write your trading strategy in plain English. Let AI do the rest.

</div>

---

## Quick Start

```bash
# Install
pip install probablyprofit[full]

# Configure (interactive wizard)
probablyprofit setup

# Run a bot
probablyprofit run "Buy YES when price < 0.15 on high volume markets"
```

That's it. You're trading.

---

## Installation

### Full Install (Recommended)

```bash
pip install probablyprofit[full]
```

This includes all AI providers (OpenAI, Claude, Gemini), Polymarket + Kalshi integration, and all features.

### Minimal Install

```bash
# Core only
pip install probablyprofit

# Add what you need
pip install probablyprofit[anthropic]    # Claude
pip install probablyprofit[openai]       # GPT-4
pip install probablyprofit[polymarket]   # Polymarket trading
```

---

## Usage

### First Time Setup

```bash
probablyprofit setup
```

The interactive wizard will guide you through:
1. Choosing an AI provider (OpenAI, Claude, or Gemini)
2. Entering API keys
3. Optionally connecting a wallet for live trading

Your config is saved to `~/.probablyprofit/` and encrypted locally.

### Running a Bot

**Inline strategy (simplest):**
```bash
probablyprofit run "Buy underpriced markets with good volume"
```

**From a strategy file:**
```bash
probablyprofit run -s my_strategy.txt
```

**Interactive strategy builder:**
```bash
probablyprofit create-strategy
```

### Modes

| Mode | Flag | Description |
|------|------|-------------|
| Dry Run | `--dry-run` | Analyze but don't trade (default) |
| Paper | `--paper` | Trade with virtual money |
| Live | `--live` | Real money trading |

```bash
# Safe testing
probablyprofit run --dry-run "..."

# Paper trading with $10k virtual capital
probablyprofit run --paper --paper-capital 10000 "..."

# Live trading (be careful!)
probablyprofit run --live "..."
```

### Other Commands

```bash
probablyprofit markets              # List active markets
probablyprofit markets -q "bitcoin" # Search markets
probablyprofit status               # Show configuration
probablyprofit balance              # Check wallet balance
probablyprofit positions            # View open positions
probablyprofit backtest -s strat.txt  # Backtest a strategy
probablyprofit dashboard            # Launch web UI
```

---

## Writing Strategies

Strategies are natural language instructions that tell the AI how to trade.

### Simple Example

```
Buy YES when price is below 0.20 and volume is above $5,000.
Bet $10 per trade.
Avoid markets I don't understand.
```

### Detailed Example

```
You are a value investor in prediction markets.

GOAL: Find mispriced markets where the crowd is wrong.

ENTRY RULES:
- BUY YES when market price < your estimated probability by 15%+
- BUY NO when market price > your estimated probability by 15%+
- Minimum volume: $5,000
- Trade size: $10-20 per position

AVOID:
- Markets you don't understand
- Prices between 40-60% (too uncertain)
- Markets resolving in <24 hours

RISK:
- Maximum 5 open positions
- Confidence 0.6-0.9 based on conviction
```

See `examples/strategies/` for more templates.

---

## Configuration

### Environment Variables

You can also configure via environment variables:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export OPENAI_API_KEY=sk-...
export PRIVATE_KEY=0x...  # Ethereum wallet for Polymarket
```

### Config Files

- `~/.probablyprofit/config.yaml` - Settings
- `~/.probablyprofit/credentials.yaml` - API keys (restricted permissions)

---

## Features

- **Multi-AI Support** - Claude, GPT-4, Gemini (or ensemble voting)
- **Multi-Platform** - Polymarket & Kalshi
- **Risk Management** - Position sizing, Kelly criterion, exposure limits
- **Intelligence Layer** - News, Twitter, Reddit sentiment
- **Paper Trading** - Test without real money
- **Backtesting** - Historical simulation
- **Web Dashboard** - Real-time monitoring UI
- **Plugin System** - Extend with custom logic

---

## Python API

For programmatic use:

```python
import asyncio
from probablyprofit import PolymarketClient, AnthropicAgent, RiskManager

async def main():
    client = PolymarketClient(private_key="0x...")
    risk = RiskManager(initial_capital=1000.0)

    agent = AnthropicAgent(
        client=client,
        risk_manager=risk,
        api_key="sk-ant-...",
        strategy_prompt="Buy underpriced markets",
    )

    await agent.run_loop()

asyncio.run(main())
```

---

## Disclaimer

**This software is for educational purposes only. Not financial advice.**

- Trading involves risk of loss
- Past performance doesn't guarantee future results
- Only trade with money you can afford to lose
- The authors are not responsible for any losses
- Always do your own research

---

## License

MIT License - see [LICENSE](LICENSE)

---

## Links

- [GitHub](https://github.com/randomness11/probablyprofit)
- [Issues](https://github.com/randomness11/probablyprofit/issues)
- [Discussions](https://github.com/randomness11/probablyprofit/discussions)
