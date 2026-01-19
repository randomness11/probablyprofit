# Configuration

All configuration is done via environment variables in `.env`.

## AI Provider Keys

You need at least one AI provider configured.

| Variable | Provider | Model |
|----------|----------|-------|
| `OPENAI_API_KEY` | OpenAI | GPT-4, GPT-4o |
| `GOOGLE_API_KEY` | Google | Gemini 1.5 Pro |
| `ANTHROPIC_API_KEY` | Anthropic | Claude 3 |
| `PERPLEXITY_API_KEY` | Perplexity | News context |

## Polymarket Credentials

Required for live trading:

```bash
POLYMARKET_API_KEY=your-api-key
POLYMARKET_API_SECRET=your-secret
POLYMARKET_API_PASSPHRASE=your-passphrase
```

Get these from [Polymarket API Settings](https://polymarket.com/profile/api).

## Risk Settings

```bash
INITIAL_CAPITAL=1000.0  # Starting capital for risk calculations
```

Additional risk settings are configured programmatically via the `RiskManager`.

## Optional Features

```bash
# SQLite persistence for trade history
ENABLE_PERSISTENCE=true

# Web dashboard
ENABLE_WEB_DASHBOARD=false
WEB_DASHBOARD_PORT=8000
```

## Example .env

```bash
# AI Provider (pick one or more)
OPENAI_API_KEY=sk-...

# Polymarket
POLYMARKET_API_KEY=...
POLYMARKET_API_SECRET=...
POLYMARKET_API_PASSPHRASE=...

# Trading
INITIAL_CAPITAL=500.0
```
