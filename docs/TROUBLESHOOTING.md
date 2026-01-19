# Troubleshooting Guide

Common issues and their solutions when using ProbablyProfit.

## Installation Issues

### "Package requires Python >=3.10"
**Problem:** Your Python version is too old.
**Solution:** Install Python 3.10 or newer:
```bash
# macOS
brew install python@3.11

# Ubuntu/Debian
sudo apt install python3.11
```

### Missing Dependencies
**Problem:** Import errors for optional packages like `websockets` or `aiosqlite`.
**Solution:** Install the required extras:
```bash
# Full install (recommended)
pip install probablyprofit[full]

# Or specific extras
pip install probablyprofit[polymarket,db]
```

## Configuration Issues

### "No AI providers configured"
**Problem:** No API keys are set for AI providers.
**Solution:** Set at least one API key in your `.env` file:
```bash
# Choose one or more:
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...
```

### "Kill switch is ACTIVE"
**Problem:** The trading bot is blocked by the kill switch.
**Solution:** The kill switch can be activated by:
1. A file at `/tmp/probablyprofit.stop`
2. Maximum drawdown being exceeded
3. Manual activation via API

To deactivate:
```bash
# Remove the file
rm /tmp/probablyprofit.stop

# Or via API
curl -X POST http://localhost:8000/api/emergency-stop/deactivate
```

### "Private key not configured"
**Problem:** Wallet private key is missing for live/paper trading.
**Solution:** Add your Polygon wallet private key to `.env`:
```bash
PRIVATE_KEY=0x...your_private_key_here...
```
**Security:** Never commit this file to git!

## Runtime Issues

### API Rate Limits
**Problem:** "Rate limit exceeded" errors from AI providers or Polymarket.
**Solution:** Increase the loop interval in your config:
```bash
LOOP_INTERVAL=120  # Wait 2 minutes between iterations
```

### WebSocket Connection Failed
**Problem:** "websockets package not installed" warning.
**Solution:** Install websockets:
```bash
pip install websockets>=12.0
```

### Database Errors
**Problem:** "no such table" or database connection errors.
**Solution:** Initialize the database:
```bash
# Run migrations
alembic upgrade head
```

### "Balance is 0" on Testnet
**Problem:** No funds for paper trading.
**Solution:** Paper trading uses simulated funds. For live trading on testnet, you need test USDC. Get some from the Polymarket faucet.

## Trading Issues

### Orders Not Executing
**Problem:** Agent shows "DRY RUN" but you want real trades.
**Solution:** Remove the `--dry-run` flag or set:
```bash
DRY_RUN=false
```
Then confirm with `--confirm-live` flag.

### Position Size Too Small
**Problem:** "Position size below minimum" rejection.
**Solution:** The minimum order size on Polymarket is typically $1. Check your `MAX_POSITION_SIZE` config.

### Risk Limits Rejecting Trades
**Problem:** Agent keeps saying "Risk check failed".
**Solution:** Review your risk limits in `.env`:
```bash
MAX_POSITION_SIZE=100     # Maximum per trade
MAX_TOTAL_EXPOSURE=1000   # Maximum total portfolio
MAX_DAILY_LOSS=200        # Daily loss limit
```

## Debugging Tips

### Enable Debug Logging
```bash
LOG_LEVEL=DEBUG python -m probablyprofit.main ...
```

### Check Agent Status
```bash
curl http://localhost:8000/api/status
```

### View Recent Logs
Logs are written via `loguru` to stderr. For file logging:
```python
from loguru import logger
logger.add("probablyprofit.log", rotation="1 day")
```

### Inspect the Database
```bash
sqlite3 probablyprofit.db
sqlite> .tables
sqlite> SELECT * FROM trades ORDER BY timestamp DESC LIMIT 10;
```

## Getting Help

If you're still stuck:
1. Check the [GitHub Issues](https://github.com/randomness11/probablyprofit/issues)
2. Open a new issue with:
   - Your Python version (`python --version`)
   - Your OS
   - The full error message
   - Relevant config (redact secrets!)
