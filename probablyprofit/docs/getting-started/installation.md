# Installation

## Prerequisites

- Python 3.9 or higher
- pip (Python package manager)
- A Polymarket account
- API keys for at least one AI provider (OpenAI, Google, or Anthropic)

## Install from PyPI

```bash
pip install probablyprofit
```

## Install from Source

```bash
git clone https://github.com/randomness11/probablyprofit.git
cd probablyprofit
pip install -e .
```

## Development Installation

For contributing or modifying the code:

```bash
pip install -e ".[dev]"
```

This installs additional tools: pytest, black, isort, mypy.

## Verify Installation

```bash
probablyprofit --version
probablyprofit --help
```

You should see the version number and available commands.

## Next Steps

- [Quick Start Guide](quickstart.md) — Get your first bot running
- [Configuration](configuration.md) — Set up API keys and settings
