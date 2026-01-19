# probablyprofit Deployment Guide

## Quick Start

```bash
# 1. Clone and setup
git clone <repo-url>
cd polymarket-ai-bot

# 2. Configure environment
cp .env.example .env
# Edit .env with your API keys

# 3. Deploy (dry-run mode by default)
./deploy.sh
```

## Deployment Modes

### 1. Dry-Run Mode (Default)
Safe mode - analyzes markets but doesn't execute trades.

```bash
./deploy.sh
# or
docker compose -f probablyprofit/docker-compose.yml up -d
```

Dashboard: http://localhost:8000

### 2. Paper Trading Mode
Simulates trades with virtual money. Perfect for testing strategies.

```bash
./deploy.sh paper
```

Dashboard: http://localhost:8001

Configuration:
```env
PAPER_CAPITAL=10000  # Starting virtual capital
```

### 3. Live Trading Mode
**REAL MONEY** - Use with caution!

```bash
./deploy.sh live
```

Requires confirmation and valid:
- `PRIVATE_KEY` for Polymarket

### 4. Ensemble Mode
Uses multiple AI providers for consensus-based decisions.

```bash
./deploy.sh ensemble
```

Requires API keys for multiple providers (OpenAI, Anthropic, Google).

### 5. Backtest Mode
Historical simulation with synthetic data.

```bash
./deploy.sh backtest
```

## Configuration

### Required Environment Variables

For Polymarket:
```env
PRIVATE_KEY=your_polygon_private_key
INITIAL_CAPITAL=1000.0
```

For AI (at least one required):
```env
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...
ANTHROPIC_API_KEY=sk-ant-...
```

### Optional Features

```env
# Web Dashboard
ENABLE_WEB_DASHBOARD=true
WEB_DASHBOARD_PORT=8000

# Data Persistence
ENABLE_PERSISTENCE=true

# Intelligence Layer (enhanced analysis)
PERPLEXITY_API_KEY=pplx-...
TWITTER_BEARER_TOKEN=...
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
```

## Trading Configuration

Override via environment or CLI:

| Variable | CLI Flag | Options |
|----------|----------|---------|
| `PLATFORM` | `--platform` | polymarket |
| `STRATEGY` | `--strategy` | mean-reversion, momentum, value, contrarian, volatility, calendar, arbitrage, news, custom |
| `AGENT` | `--agent` | openai, gemini, anthropic, ensemble, fallback |
| `INTERVAL` | `--interval` | seconds between loops |
| `SIZING` | `--sizing` | manual, fixed_pct, kelly, confidence_based, dynamic |

## Commands

```bash
# Start (dry-run)
./deploy.sh

# Start (paper trading)
./deploy.sh paper

# Start (live trading)
./deploy.sh live

# Start (ensemble)
./deploy.sh ensemble

# Run backtest
./deploy.sh backtest

# Run locally (no Docker)
./deploy.sh local

# View logs
./deploy.sh logs

# Stop all services
./deploy.sh stop

# Build only
./deploy.sh build
```

## Docker Commands

```bash
# Build image
docker compose -f probablyprofit/docker-compose.yml build

# Start specific profile
docker compose -f probablyprofit/docker-compose.yml --profile paper up -d

# View logs
docker compose -f probablyprofit/docker-compose.yml logs -f

# Stop
docker compose -f probablyprofit/docker-compose.yml down

# Shell into container
docker exec -it probablyprofit_bot /bin/bash
```

## Local Development

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Build frontend
cd frontend && npm install && npm run build && cd ..

# Run
python -m probablyprofit.main --dry-run --strategy mean-reversion
```

## Architecture

```
probablyprofit/
├── agent/              # AI agents (OpenAI, Gemini, Anthropic)
├── api/                # Platform clients (Polymarket)
├── backtesting/        # Historical simulation
├── intelligence/       # News & alpha signal sources
├── resilience/         # Retry, circuit breaker, rate limiter
├── risk/               # Risk management & position sizing
├── storage/            # SQLite persistence
├── trading/            # Paper trading engine
└── web/                # FastAPI + React dashboard
```

## Monitoring

The web dashboard provides:
- Real-time status and P&L
- Position tracking
- Trade history
- Risk exposure analysis
- Arbitrage opportunity scanner
- Paper trading portfolio

## Troubleshooting

### Container won't start
```bash
# Check logs
docker compose -f probablyprofit/docker-compose.yml logs probablyprofit

# Rebuild
docker compose -f probablyprofit/docker-compose.yml build --no-cache
```

### API errors
1. Verify API keys in `.env`
2. Check rate limits (use `--interval 120` for slower polling)
3. Enable fallback agent: `--agent fallback`

### Frontend not loading
```bash
# Rebuild frontend
cd frontend && npm run build && cd ..
```

## Health Check

```bash
# Check API status
curl http://localhost:8000/api/status

# Check health endpoint
curl http://localhost:8000/health
```

## Security Notes

- **NEVER** commit `.env` to version control
- Use read-only volume mounts for `.env` in Docker
- Run as non-root user (default in Dockerfile)
- Start with `--dry-run` always
