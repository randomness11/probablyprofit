# Architecture

This document explains how probablyprofit is structured and how to extend it.

## Overview

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Your Strategy  │ ──► │   AI Agent   │ ──► │   Polymarket    │
│  (strategy.txt) │     │ (GPT-4/etc)  │     │   (Real Trades) │
└─────────────────┘     └──────────────┘     └─────────────────┘
```

## Directory Structure

```
probablyprofit/
├── main.py              # Entry point, CLI parsing, agent initialization
│
├── agent/               # AI Agents
│   ├── base.py          # BaseAgent: observe → decide → act loop
│   ├── openai_agent.py  # GPT-4 integration
│   ├── gemini_agent.py  # Google Gemini integration
│   ├── anthropic_agent.py # Claude integration
│   ├── ensemble.py      # Multi-agent consensus voting
│   ├── strategy.py      # Strategy classes (Mean Reversion, News, Custom)
│   └── intelligence.py  # News context via Perplexity API
│
├── api/                 # Platform Clients
│   ├── client.py        # PolymarketClient (Gamma API + CLOB)
│   ├── kalshi_client.py # KalshiClient
│   └── platform.py      # Platform abstraction
│
├── risk/                # Risk Management
│   └── manager.py       # RiskManager (limits, Kelly sizing, stop losses)
│
├── plugins/             # Plugin System
│   ├── registry.py      # PluginRegistry for discovery/registration
│   ├── base.py          # Base plugin classes
│   └── hooks.py         # Hook system for lifecycle events
│
├── storage/             # Persistence
│   └── database.py      # SQLite storage for trades/decisions
│
├── backtesting/         # Simulation
│   ├── engine.py        # BacktestEngine
│   └── data.py          # MockDataGenerator
│
├── web/                 # Web Dashboard
│   └── server.py        # FastAPI server
│
└── examples/            # Example Strategies
    └── *.txt            # Strategy templates
```

## Core Abstractions

### BaseAgent

The heart of the framework. Implements the **observe → decide → act** loop:

```python
class BaseAgent:
    async def observe(self) -> Observation:
        # Fetch markets, positions, balance
        
    async def decide(self, observation: Observation) -> Decision:
        # ABSTRACT: Subclasses implement trading logic
        
    async def act(self, decision: Decision) -> bool:
        # Execute trade via platform client
        
    async def run_loop(self):
        while self._running:
            obs = await self.observe()
            decision = await self.decide(obs)
            await self.act(decision)
            await asyncio.sleep(self.loop_interval)
```

### Decision

Trading decision returned by agents:

```python
@dataclass
class Decision:
    action: str           # "buy", "sell", "hold"
    market_id: str        # Which market
    outcome: str          # "Yes" or "No"
    size: float           # Number of shares
    price: float          # Limit price (0-1)
    reasoning: str        # Why this trade
    confidence: float     # 0-1 confidence score
```

### RiskManager

Enforces trading limits:

- `max_position_size`: Cap on single trade size
- `max_daily_loss`: Stop trading if daily loss exceeded
- `max_exposure`: Total capital at risk limit
- Kelly criterion position sizing

### PluginRegistry

Extensibility system:

```python
@registry.register("my_strategy", PluginType.STRATEGY)
class MyStrategy(StrategyPlugin):
    ...
```

## Data Flow

1. **CLI parses args** → selects platform, agent, strategy
2. **Platform client initialized** → connects to Polymarket/Kalshi API
3. **Strategy loaded** → from file or built-in
4. **Agent created** → with client, risk manager, strategy prompt
5. **Loop starts**:
   - `observe()` → fetch live market data
   - `decide()` → send to AI, get trading decision
   - `act()` → execute via platform client (or log if dry-run)
   - Sleep and repeat

## Extending the Framework

| Want to... | Do this |
|------------|---------|
| Add new AI provider | Create `agent/new_agent.py`, inherit `BaseAgent` |
| Add new platform | Create `api/new_client.py`, implement same interface |
| Add strategy type | Use plugin system or modify `agent/strategy.py` |
| Add data source | Create plugin with `PluginType.DATA_SOURCE` |

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed examples.
