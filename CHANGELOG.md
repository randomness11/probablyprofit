# Changelog

All notable changes to ProbablyProfit will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2025-01-11

### Added

- **CLI Experience**: New `probablyprofit` command-line tool
  - `probablyprofit setup` - Interactive configuration wizard
  - `probablyprofit run "strategy"` - Run bot with inline strategy
  - `probablyprofit run -s file.txt` - Run bot with strategy file
  - `probablyprofit markets` - List active prediction markets
  - `probablyprofit status` - Check configuration status
  - `probablyprofit create-strategy` - Interactive strategy builder
  - `probablyprofit backtest` - Backtest strategies
  - `probablyprofit dashboard` - Launch web UI

- **Streaming Output**: Real-time AI thinking display with `--stream` flag

- **Configuration System**
  - Config stored in `~/.probablyprofit/`
  - Secure credentials storage with 0600 permissions
  - Support for environment variables, .env files, and config files

- **Multi-AI Support**
  - OpenAI (GPT-4o)
  - Anthropic (Claude Sonnet)
  - Google (Gemini 2.0)
  - Ensemble voting mode
  - Fallback chains

- **Trading Platforms**
  - Polymarket integration
  - Kalshi integration

- **Risk Management**
  - Position sizing
  - Kelly criterion
  - Max exposure limits
  - Daily loss limits

- **Trading Modes**
  - Dry run (default, safe)
  - Paper trading with virtual capital
  - Live trading

- **Intelligence Layer**
  - News via Perplexity API
  - Twitter sentiment
  - Reddit sentiment
  - Google Trends

- **Modular Dependencies**
  - `pip install probablyprofit` - Core only
  - `pip install probablyprofit[full]` - Everything
  - Individual extras: `[openai]`, `[anthropic]`, `[polymarket]`, etc.

### Security

- Private keys stored locally only
- Credentials file has restricted permissions
- API keys never logged

### Documentation

- Complete README with quick start guide
- Example strategies in `examples/strategies/`
- CLI help for all commands

## [Unreleased]

### Planned

- PyPI package publishing
- Shell tab completion
- More AI providers
- Advanced backtesting
- Strategy optimization
