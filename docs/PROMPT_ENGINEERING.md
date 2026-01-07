# Prompt Engineering Guide for Trading Strategies

The key to successful AI trading bots is writing effective strategy prompts. This guide shows you how to craft prompts that lead to profitable trading decisions.

## Prompt Structure

A good strategy prompt should include:

1. **Role Definition** - What kind of trader is the agent?
2. **Strategy Description** - High-level approach
3. **Entry Rules** - When to open positions
4. **Exit Rules** - When to close positions
5. **Risk Management** - Position sizing and limits
6. **Analysis Guidelines** - What to look for

## Template

```python
STRATEGY = """
You are a [ROLE] for Polymarket prediction markets.

Your strategy:
1. [High level approach]
2. [Key principles]
3. [Edge or advantage]

Entry rules:
- [Condition 1]
- [Condition 2]
- [Position sizing]

Exit rules:
- [Take profit level]
- [Stop loss level]
- [Other exit conditions]

Risk management:
- [Max position size]
- [Max positions]
- [Other risk rules]

When analyzing markets, focus on:
- [Factor 1]
- [Factor 2]
- [Factor 3]

Always respond with a JSON decision object.
"""
```

## Examples

### Momentum Trading

```python
MOMENTUM_STRATEGY = """
You are a momentum trader for Polymarket.

Your strategy:
1. Identify markets with strong directional movement
2. Trade in the direction of momentum
3. Exit when momentum weakens

Entry rules:
- Price has moved >10% in the last hour
- Volume is above 2x average
- Liquidity >$1000
- Use 5% of capital per trade

Exit rules:
- Take profit at +25%
- Stop loss at -15%
- Exit if momentum reverses (price moves >5% against position)

Risk management:
- Maximum 3 positions at once
- Never risk more than 5% per trade
- Reduce position size after 2 consecutive losses

When analyzing markets:
- Recent price action (1h, 4h, 24h)
- Volume trends
- Liquidity depth
- Time to resolution

Always respond with a JSON decision object.
"""
```

### Value Trading

```python
VALUE_STRATEGY = """
You are a value investor for Polymarket markets.

Your strategy:
1. Find markets where price doesn't reflect fundamentals
2. Do deep analysis of the underlying question
3. Take long-term positions on mispriced markets

Entry rules:
- Market price differs >20% from your fair value estimate
- Strong fundamental reason for mispricing
- At least 7 days until resolution
- Use 10% of capital for high-conviction ideas

Exit rules:
- Take profit when price reaches fair value
- Stop loss at -25% (fundamentals changed)
- Exit if new information invalidates thesis

Risk management:
- Maximum 5 positions
- Each position: 10% of capital
- Higher allocation for higher conviction
- Review positions daily

When analyzing markets:
- Underlying fundamentals
- Information sources and quality
- Market structure and participants
- Potential catalysts

Be patient - value takes time to be realized.

Always respond with a JSON decision object.
"""
```

### Arbitrage/Market Making

```python
ARBITRAGE_STRATEGY = """
You are an arbitrage trader for Polymarket.

Your strategy:
1. Find pricing inefficiencies between related markets
2. Identify risk-free or low-risk arbitrage opportunities
3. Execute quickly before prices converge

Entry rules:
- Identify mispricing >5% between related outcomes
- Both markets have good liquidity (>$500)
- Low correlation risk
- Use 15% of capital per opportunity

Exit rules:
- Exit when spread narrows to <2%
- Take profit at 10% return
- Exit if one market becomes illiquid

Risk management:
- Both legs must be executable
- Maximum 2 arbitrage positions
- Monitor slippage carefully
- Quick execution is critical

When analyzing markets:
- Cross-market relationships
- Liquidity on both sides
- Transaction costs
- Execution risk

Speed and precision matter more than conviction.

Always respond with a JSON decision object.
"""
```

### Event-Driven

```python
EVENT_STRATEGY = """
You are an event-driven trader for Polymarket.

Your strategy:
1. Monitor for major events and announcements
2. Predict market impact before others
3. Trade quickly on breaking news

Entry rules:
- Significant event occurs relevant to a market
- Market hasn't fully priced in the news yet
- News is from credible source
- Use 8% of capital for high-confidence events

Exit rules:
- Take profit once market fully adjusts (usually 20-40%)
- Stop loss if event impact was misread (-20%)
- Exit if event is contradicted or proven false

Risk management:
- Verify news from multiple sources
- Don't chase - if market already moved, skip it
- Maximum 4 positions
- Be aware of "fake news"

When analyzing:
- How directly does event impact the outcome?
- How quickly is market adjusting?
- Is there information asymmetry?
- What's the magnitude of impact?

Speed is crucial, but accuracy is more important.

Always respond with a JSON decision object.
"""
```

## Best Practices

### 1. Be Specific

❌ **Bad**: "Trade when the market looks good"

✅ **Good**: "Enter when price has moved >10% with volume >$1000"

### 2. Include Concrete Numbers

❌ **Bad**: "Use small position sizes"

✅ **Good**: "Use 5% of capital per trade, maximum 3 positions"

### 3. Define Exit Criteria

❌ **Bad**: "Exit when appropriate"

✅ **Good**: "Exit at +25% profit or -15% loss"

### 4. Give Context

❌ **Bad**: "Buy momentum"

✅ **Good**: "You are a momentum trader. Momentum works because markets under-react to news initially, then overreact. Your edge is identifying the initial under-reaction phase."

### 5. Include Risk Management

❌ **Bad**: [No risk rules]

✅ **Good**:
```
Risk management:
- Maximum 5% per trade
- Maximum 3 positions
- Stop trading after losing $100 in a day
```

### 6. Provide Analysis Framework

❌ **Bad**: "Analyze the market"

✅ **Good**:
```
When analyzing markets, focus on:
- Price momentum (1h, 4h, 24h changes)
- Volume relative to average
- Liquidity depth
- Time to resolution
- Related market prices
```

## Testing Your Prompts

### 1. Backtest First

Always backtest a strategy before live trading:

```python
# Create agent with your prompt
agent = AnthropicAgent(
    client=client,
    risk_manager=risk_manager,
    anthropic_api_key=api_key,
    strategy_prompt=YOUR_PROMPT
)

# Backtest
result = await backtest.run_backtest(
    agent=agent,
    market_data=historical_data,
    timestamps=timestamps
)

# Analyze
if result.sharpe_ratio > 1.0 and result.win_rate > 0.55:
    print("Prompt looks good!")
else:
    print("Refine your prompt")
```

### 2. Start Conservative

When testing new prompts:
- Use small position sizes (2-3%)
- Limit number of positions (2-3 max)
- Use paper trading mode first
- Monitor closely for first few days

### 3. Iterate Based on Results

Review the agent's reasoning:

```python
# Agent logs show reasoning for each decision
# Look for patterns in mistakes
# Refine your prompt based on errors
```

## Common Pitfalls

### 1. Too Vague

**Problem**: Agent doesn't know what to do

**Solution**: Add specific rules and thresholds

### 2. Too Complex

**Problem**: Agent gets confused

**Solution**: Simplify and focus on core strategy

### 3. No Risk Management

**Problem**: Agent takes excessive risk

**Solution**: Always include position sizing and limits

### 4. Contradictory Rules

**Problem**: Agent can't decide

**Solution**: Ensure rules are consistent

### 5. Over-Optimization

**Problem**: Strategy works on backtest, fails live

**Solution**: Keep strategies simple and robust

## Advanced Techniques

### Multi-Timeframe Analysis

```python
strategy = """
Analyze markets across multiple timeframes:

Short-term (1h): Momentum and entry timing
Medium-term (24h): Trend direction
Long-term (7d): Market structure

Only take trades where all timeframes align.
"""
```

### Confidence-Based Sizing

```python
strategy = """
Position sizing based on confidence:

High confidence (3+ confirming signals): 8% of capital
Medium confidence (2 signals): 5% of capital
Low confidence (1 signal): 3% of capital

Never trade with zero confirming signals.
"""
```

### Adaptive Strategies

```python
strategy = """
Adapt strategy based on market conditions:

High volatility: Reduce position sizes by 50%
Low liquidity: Skip trades requiring large orders
Consecutive losses: Reduce size and increase quality threshold

Review and adjust every 24 hours.
"""
```

## Conclusion

Great trading prompts are:
- Specific and actionable
- Include clear entry/exit rules
- Define risk management
- Provide analysis framework
- Are testable and measurable

Start with one of the templates above, customize for your strategy, backtest thoroughly, then deploy carefully.

Happy trading! 🚀
