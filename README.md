# [±] ProbablyProfit

<div align="center">

### Your hedge fund. One prompt away.

[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-3776ab?style=flat-square&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](https://opensource.org/licenses/MIT)
[![Status](https://img.shields.io/badge/Status-Beta-orange?style=flat-square)](https://github.com/randomness11/probablyprofit)
[![Twitter](https://img.shields.io/badge/Twitter-@ankitkr0-1da1f2?style=flat-square&logo=twitter&logoColor=white)](https://twitter.com/ankitkr0)

> **⚠️ BETA SOFTWARE** — This project is under active development and testing. Use at your own risk. Start with paper trading. Never risk money you can't afford to lose.

**[Quick Start](#60-second-setup)** · **[Examples](#real-examples)** · **[Python API](#python-api)** · **[CLI](#cli-reference)**

</div>

---

```
You are an elite prediction market trader.

Find markets where the crowd is wrong. Buy YES when price is 20%+ below
true probability. Buy NO when price is 20%+ above. Size bets using Kelly
criterion. Never risk more than 5% per trade. Exit at 2x or cut losses at -30%.

Avoid: politics you don't understand, markets < $5k volume, coin flips.
```

**That's it.** That's your entire trading bot.

One prompt. Claude reads 500+ markets. Finds mispriced bets. Executes trades. Manages risk. 24/7.

```bash
pip install probablyprofit[full]
probablyprofit run -s strategy.txt --live
```

---

## What This Is

Everyone's building AI wrappers. We built **infrastructure for AI-native trading**.

| Platform | What It Is | ProbablyProfit |
|----------|-----------|----------------|
| **Polymarket** | $2B+ volume prediction market, crypto rails | ✅ Full support |
| **Kalshi** | Regulated US exchange, real USD | ✅ Full support |

**You describe your edge in English. The AI handles:**
- Scanning hundreds of markets in seconds
- Calculating expected value using reasoning
- Sizing positions with Kelly criterion
- Executing via CLOB (limit orders, not AMM slippage)
- Tracking P&L, managing risk, never sleeping

---

## 60-Second Setup

```bash
# 1. Install
pip install probablyprofit[full]

# 2. Configure
cp .env.example .env
# Add: ANTHROPIC_API_KEY and POLYMARKET_PRIVATE_KEY

# 3. Paper trade (virtual money - start here!)
probablyprofit run "Buy YES under 0.30 on high-volume markets" --paper

# 4. Go live when confident
probablyprofit run -s my_strategy.txt --live
```

---

## The Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      YOUR STRATEGY                          │
│         "Buy undervalued YES on election markets"           │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    AI DECISION ENGINE                        │
│                                                              │
│   ┌─────────┐    ┌─────────┐    ┌─────────┐                │
│   │ Claude  │    │  GPT-4  │    │ Gemini  │   ← Pick one   │
│   └─────────┘    └─────────┘    └─────────┘     or all     │
│                        ↓                                     │
│              [Ensemble Mode: 2/3 consensus]                  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    RISK MANAGEMENT                           │
│                                                              │
│   Kelly Sizing │ Position Limits │ Stop Loss │ Take Profit  │
│   Max Drawdown │ Correlation Checks │ Exposure Caps         │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                   ORDER MANAGEMENT                           │
│                                                              │
│   Order Lifecycle │ Fill Tracking │ Partial Fills           │
│   Cancel/Modify │ Reconciliation │ Event Callbacks          │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────┐         ┌────────────────────────────┐
│     POLYMARKET       │         │          KALSHI            │
│   Crypto / Global    │         │     Regulated / US         │
│   USDC Settlement    │         │     USD Settlement         │
└──────────────────────┘         └────────────────────────────┘
```

---

## Real Examples

### Value Investor Strategy

Save as `value.txt`:

```
You are a value investor for prediction markets.

EDGE: Markets are inefficient. Crowds overreact to news and
underreact to base rates. Find the gap.

BUY YES when:
- Your estimated probability is 20%+ higher than market price
- Resolution criteria is unambiguous
- Volume > $10,000 (liquidity matters)
- Time to resolution > 7 days

BUY NO when:
- Market is 20%+ overpriced vs your estimate
- Same liquidity/clarity requirements

SIZING:
- Base: $20 per trade
- High conviction (30%+ edge): $50
- Max 5 concurrent positions
- Never more than 20% of bankroll at risk

EXIT:
- Take profit at 2x
- Stop loss at -30%
- Close 24h before resolution

AVOID:
- Markets you don't understand
- Prices 0.40-0.60 (coin flips)
- Celebrity/meme markets
- Ambiguous resolution criteria
```

Run it:
```bash
probablyprofit run -s value.txt --paper
```

### More Strategy Ideas

<details>
<summary><b>Arbitrage Hunter</b></summary>

```
Find price discrepancies between related markets.
If "Trump wins" is 0.45 and "Biden wins" is 0.58, something's wrong.
The two should sum to ~1.00. Trade the gap.
```
</details>

<details>
<summary><b>News Reactor</b></summary>

```
You have access to recent knowledge. Find news that markets haven't priced in.
When you find significant news affecting an outcome:
- Verify the source
- Estimate probability shift
- Enter within 5 minutes
- Size based on edge magnitude
```
</details>

<details>
<summary><b>Contrarian</b></summary>

```
When markets move 20%+ in a day on no real news, fade the move.
Crowds overreact. Reversion is your edge.
Wait for the spike. Enter against it. Exit when price normalizes.
```
</details>

<details>
<summary><b>Base Rate Specialist</b></summary>

```
Focus on categories where you know historical base rates.
- Elections: incumbents win X% of the time
- Sports: home teams win Y% of the time
Find markets where price diverges from base rate.
```
</details>

---

## Python API

For builders who want full control:

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
    # Setup
    client = PolymarketClient(private_key="0x...")

    risk = RiskManager(
        initial_capital=1000.0,
        limits=RiskLimits(
            max_position_size=50.0,
            max_total_exposure=500.0,
            max_daily_loss=100.0
        )
    )

    orders = OrderManager(client=client)

    # Create AI agent
    agent = AnthropicAgent(
        client=client,
        risk_manager=risk,
        order_manager=orders,
        strategy_prompt=open("value.txt").read()
    )

    # Callbacks
    orders.on_fill = lambda o, f: print(f"Filled: {f.size}@{f.price}")
    orders.on_complete = lambda o: print(f"Complete: {o.order_id}")

    # Run
    await agent.run_loop()

asyncio.run(main())
```

---

## Features

| Feature | Description |
|---------|-------------|
| **Plain English Strategies** | No code needed. Describe your edge like you'd tell a friend. |
| **Multi-AI Support** | Claude, GPT-4, Gemini. Or ensemble mode for consensus. |
| **Order Management** | Full lifecycle: submit → partial fills → complete. Event callbacks. |
| **Risk Engine** | Kelly sizing, position limits, stop-loss, take-profit, max drawdown. |
| **Dual Platform** | Polymarket + Kalshi. Same interface. |
| **Paper Trading** | Test strategies with virtual money first. |
| **Backtesting** | Validate on historical data. |
| **WebSocket Feeds** | Real-time price streams. |
| **Web Dashboard** | Monitor positions and P&L in browser. |
| **Persistence** | SQLite storage for trades and metrics. |

---

## CLI Reference

```bash
# Trading
probablyprofit run "strategy" --paper   # Paper trading
probablyprofit run -s file.txt --live   # Live trading
probablyprofit run --dry-run "..."      # Analyze only (no trades)

# Market data
probablyprofit markets                  # List active markets
probablyprofit markets -q "trump"       # Search markets
probablyprofit market <id>              # Market details

# Portfolio
probablyprofit balance                  # Wallet balance
probablyprofit positions                # Open positions
probablyprofit orders                   # View orders
probablyprofit history                  # Trade history

# Tools
probablyprofit setup                    # Interactive config
probablyprofit backtest -s strat.txt    # Backtest strategy
probablyprofit dashboard                # Launch web UI
```

---

## Configuration

### Environment Variables

```bash
# AI Provider (pick one)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...

# Polymarket
POLYMARKET_PRIVATE_KEY=0x...

# Kalshi (optional)
KALSHI_API_KEY=...
KALSHI_PRIVATE_KEY_PATH=/path/to/key.pem
```

### Config File (optional)

```yaml
# ~/.probablyprofit/config.yaml

agent:
  default_model: claude-sonnet-4-20250514
  loop_interval: 300

risk:
  initial_capital: 1000.0
  max_position_size: 50.0
  max_total_exposure: 0.5
  max_drawdown: 0.20

platforms:
  polymarket:
    enabled: true
  kalshi:
    enabled: false
```

---

## Platforms

| Platform | Type | Region | Settlement | Auth |
|----------|------|--------|------------|------|
| [Polymarket](https://polymarket.com) | Crypto | Global* | USDC on Polygon | Ethereum wallet |
| [Kalshi](https://kalshi.com) | Regulated | US only | USD | RSA key pair |

*Polymarket blocks US IPs but doesn't KYC.

---

## Why Prediction Markets + AI

Prediction markets are the most efficient price discovery mechanism. But they're also inefficient:

- **Information asymmetry** — You know things the crowd doesn't
- **Behavioral biases** — Overreaction to news, underreaction to base rates
- **Liquidity gaps** — Small markets are mispriced
- **Speed** — News moves faster than markets

AI changes everything:
- Read and reason about hundreds of markets at once
- Apply your edge consistently without emotion
- Execute 24/7 without fatigue
- Scale your insight

**ProbablyProfit = Your edge × AI execution**

---

## Risk Warning

> **🚨 THIS IS BETA SOFTWARE. YOU WILL PROBABLY LOSE MONEY.**

**Seriously, read this:**

- **This software is experimental** — Bugs exist. Features may break. APIs change.
- **AI makes mistakes** — LLMs hallucinate. They will make bad trades. Count on it.
- **Trading is risky** — You can lose 100% of your capital. Many traders do.
- **Past performance means nothing** — Backtests lie. Paper trading isn't real.
- **Start small** — Paper trade first. Then $10. Then $50. Scale slowly.
- **Never risk rent money** — Only trade what you can literally set on fire.
- **This is not financial advice** — We're developers, not financial advisors.
- **You are responsible** — No refunds. No support guarantees. Your keys, your risk.

By using this software, you accept full responsibility for any losses.

---

## Contributing

PRs welcome. Key areas:
- New exchange integrations
- Strategy templates
- Risk management improvements
- Documentation

See [CONTRIBUTING.md](probablyprofit/CONTRIBUTING.md)

---

## License

MIT — see [LICENSE](LICENSE)

---

<div align="center">

Built by [@ankitkr0](https://twitter.com/ankitkr0)

**You give it a strategy. It gives you edge.**

**[± ProbablyProfit](https://github.com/randomness11/probablyprofit)**

</div>
