# probablyprofit

<div align="center">

**The "Hedge Fund in a Box" for Polymarket**

Write trading strategies in plain English. Let AI agents execute them 24/7.

</div>

---

## What is probablyprofit?

probablyprofit is an open source framework for building AI-powered trading bots on prediction markets like Polymarket.

### Key Features

- 🧠 **Multiple AI Agents** — GPT-4, Claude, Gemini, or all of them together
- 📝 **Plain English Strategies** — No coding required, write strategies in text files
- 🔒 **Risk Management** — Built-in position limits, stop losses, and Kelly sizing
- 🧪 **Dry Run Mode** — Test without risking real money
- 📊 **Web Dashboard** — Real-time monitoring UI
- 🔌 **Plugin System** — Extend with custom data sources and strategies

## Quick Start

```bash
pip install probablyprofit
probablyprofit init
probablyprofit run --dry-run
```

[Get Started →](getting-started/installation.md)

## How It Works

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Your Strategy  │ ──► │   AI Agent   │ ──► │   Polymarket    │
│  (strategy.txt) │     │ (GPT-4/etc)  │     │   (Real Trades) │
└─────────────────┘     └──────────────┘     └─────────────────┘
```

1. **You write** a strategy in plain English
2. **The AI analyzes** live market data
3. **Trades execute** based on AI decisions
