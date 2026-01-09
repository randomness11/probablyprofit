# API Reference

## Core Classes

### PolymarketClient

High-level wrapper for the Polymarket CLOB API.

```python
from probablyprofit import PolymarketClient

client = PolymarketClient(
    api_key="your_api_key",
    secret="your_secret",
    passphrase="your_passphrase",
    chain_id=137,
    testnet=False
)
```

#### Methods

##### get_markets()

Fetch available prediction markets.

```python
markets = await client.get_markets(
    active=True,  # Only active markets
    limit=100,    # Max results
    offset=0      # Pagination offset
)
```

**Returns**: `List[Market]`

##### get_market()

Get details for a specific market.

```python
market = await client.get_market(condition_id="0x123...")
```

**Returns**: `Optional[Market]`

##### place_order()

Place a limit order.

```python
order = await client.place_order(
    market_id="0x123...",
    outcome="Yes",
    side="BUY",  # or "SELL"
    size=10.0,   # Number of shares
    price=0.60   # Limit price (0-1)
)
```

**Returns**: `Optional[Order]`

##### get_positions()

Get current open positions.

```python
positions = await client.get_positions()
```

**Returns**: `List[Position]`

##### get_balance()

Get account balance in USDC.

```python
balance = await client.get_balance()
```

**Returns**: `float`

---

### BaseAgent

Abstract base class for trading agents implementing the observe-decide-act loop.

```python
from polymarket_bot.agent import BaseAgent

class MyAgent(BaseAgent):
    async def decide(self, observation):
        # Implement your strategy
        return Decision(action="hold")
```

#### Methods

##### observe()

Observe current market state.

```python
observation = await agent.observe()
```

**Returns**: `Observation` with fields:
- `timestamp`: Current time
- `markets`: List of markets
- `positions`: Current positions
- `balance`: Account balance
- `signals`: Custom signals dictionary

##### decide()

Make a trading decision (must be implemented by subclass).

```python
decision = await agent.decide(observation)
```

**Returns**: `Decision` with fields:
- `action`: "buy", "sell", or "hold"
- `market_id`: Market to trade
- `outcome`: Outcome to bet on
- `size`: Position size
- `price`: Limit price
- `reasoning`: Explanation
- `confidence`: 0-1

##### act()

Execute a trading decision.

```python
success = await agent.act(decision)
```

**Returns**: `bool`

##### run()

Start the agent loop.

```python
await agent.run()
```

---

### AnthropicAgent

AI-powered agent using Claude for decision-making.

```python
from probablyprofit import AnthropicAgent

agent = AnthropicAgent(
    client=polymarket_client,
    risk_manager=risk_manager,
    anthropic_api_key="sk-...",
    strategy_prompt=STRATEGY,
    model="claude-sonnet-4-5-20250929",
    loop_interval=300,
    temperature=1.0
)
```

#### Constructor Parameters

- `client`: PolymarketClient instance
- `risk_manager`: RiskManager instance
- `anthropic_api_key`: Anthropic API key
- `strategy_prompt`: Natural language strategy description
- `model`: Claude model ID (default: claude-sonnet-4-5-20250929)
- `name`: Agent name for logging
- `loop_interval`: Seconds between iterations
- `temperature`: Sampling temperature (0-1)

---

### RiskManager

Risk management and position sizing.

```python
from probablyprofit import RiskManager
from probablyprofit.risk import RiskLimits

limits = RiskLimits(
    max_position_size=100.0,
    max_total_exposure=1000.0,
    max_positions=5,
    max_daily_loss=200.0
)

risk_manager = RiskManager(
    limits=limits,
    initial_capital=1000.0
)
```

#### Methods

##### can_open_position()

Check if a position can be opened within risk limits.

```python
allowed = risk_manager.can_open_position(
    size=10.0,
    price=0.60,
    market_id="0x123..."
)
```

**Returns**: `bool`

##### calculate_position_size()

Calculate appropriate position size.

```python
size = risk_manager.calculate_position_size(
    price=0.60,
    confidence=0.8,
    method="kelly"  # or "fixed_pct", "confidence_based"
)
```

**Returns**: `float`

##### should_stop_loss()

Check if stop-loss should trigger.

```python
should_exit = risk_manager.should_stop_loss(
    entry_price=0.60,
    current_price=0.50,
    size=10.0,
    stop_loss_pct=0.20
)
```

**Returns**: `bool`

##### record_trade()

Record a trade for tracking.

```python
risk_manager.record_trade(
    size=10.0,
    price=0.60,
    pnl=4.0
)
```

---

### BacktestEngine

Backtesting and simulation engine.

```python
from polymarket_bot.backtesting import BacktestEngine

backtest = BacktestEngine(initial_capital=1000.0)

result = await backtest.run_backtest(
    agent=my_agent,
    market_data=historical_markets,
    timestamps=timestamps
)
```

#### BacktestResult

Returns a `BacktestResult` with:

- `total_return`: Total P&L
- `total_return_pct`: Return percentage
- `total_trades`: Number of trades
- `win_rate`: Winning trade percentage
- `sharpe_ratio`: Sharpe ratio
- `max_drawdown`: Maximum drawdown
- `equity_curve`: List of equity snapshots

---

## Data Models

### Market

```python
class Market(BaseModel):
    condition_id: str
    question: str
    description: Optional[str]
    end_date: datetime
    outcomes: List[str]
    outcome_prices: List[float]
    volume: float
    liquidity: float
    active: bool
```

### Order

```python
class Order(BaseModel):
    order_id: Optional[str]
    market_id: str
    outcome: str
    side: str  # "BUY" or "SELL"
    size: float
    price: float
    status: str
    filled_size: float
    timestamp: datetime
```

### Position

```python
class Position(BaseModel):
    market_id: str
    outcome: str
    size: float
    avg_price: float
    current_price: float
    pnl: float

    @property
    def value(self) -> float:
        """Current position value"""

    @property
    def unrealized_pnl(self) -> float:
        """Unrealized profit/loss"""
```

---

## Data Collection

### NewsCollector

Collect news from RSS feeds and APIs.

```python
from polymarket_bot.data import NewsCollector

collector = NewsCollector(
    news_api_key="your_key",
    sources=[
        "http://feeds.bbci.co.uk/news/rss.xml",
        "https://feeds.reuters.com/reuters/topNews"
    ]
)

articles = await collector.collect(hours=24)

# Search for keywords
matching = collector.search(
    keywords=["election", "trump", "biden"],
    hours=24
)
```

### SocialCollector

Collect Twitter/social data.

```python
from polymarket_bot.data import SocialCollector

collector = SocialCollector(
    twitter_bearer_token="your_token"
)

tweets = await collector.fetch_tweets(
    query="polymarket OR prediction market",
    max_results=100,
    hours=24
)

sentiment = collector.analyze_sentiment(tweets)
```

### SignalGenerator

Generate trading signals from market data.

```python
from polymarket_bot.data import SignalGenerator

signal_gen = SignalGenerator()

# Detect momentum
momentum_signal = signal_gen.detect_momentum(
    market=market,
    threshold=0.10
)

# Detect volume spikes
volume_signal = signal_gen.detect_volume_spike(
    market=market,
    threshold=2.0
)

# Generate all signals
signals = signal_gen.generate_signals(markets)
```

---

## Utilities

### setup_logging()

Configure logging.

```python
from polymarket_bot.utils import setup_logging

setup_logging(
    level="INFO",  # DEBUG, INFO, WARNING, ERROR
    log_file="bot.log"  # Optional file output
)
```

---

## Error Handling

All async methods may raise exceptions. Wrap in try/except:

```python
try:
    markets = await client.get_markets()
except Exception as e:
    logger.error(f"Error fetching markets: {e}")
```

---

## Type Hints

The framework uses type hints throughout:

```python
from typing import List, Optional
from polymarket_bot.api.client import Market, Order

async def analyze_markets(
    markets: List[Market]
) -> Optional[Order]:
    # Type-checked code
    pass
```
