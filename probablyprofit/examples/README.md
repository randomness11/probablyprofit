# Example Strategy Templates

This folder contains example strategy prompts you can use with probablyprofit.

## Available Strategies

| Strategy | Risk Level | Description |
|----------|------------|-------------|
| `conservative.txt` | Low | Capital preservation, high liquidity only |
| `aggressive.txt` | High | Force trades, bet on low-priced YES |
| `value_hunting.txt` | Medium | Find mispriced markets |
| `mean_reversion.txt` | Medium | Fade extreme prices |
| `news_driven.txt` | Medium-High | React to breaking news |

## Usage

```bash
# Use conservative strategy
python main.py --strategy custom --prompt-file examples/conservative.txt --dry-run

# Use aggressive strategy (live)
python main.py --strategy custom --prompt-file examples/aggressive.txt

# Combine with news intelligence
python main.py --strategy custom --prompt-file examples/news_driven.txt --news --dry-run
```

## Writing Your Own

Create a `.txt` file with:
1. Trading persona/style
2. Clear entry/exit rules
3. Position sizing guidelines
4. Risk preferences

The AI agent will interpret your instructions and make trading decisions accordingly.
