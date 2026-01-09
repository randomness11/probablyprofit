# Contributing to probablyprofit

Thanks for your interest in contributing! This guide will help you get started.

## Development Setup

```bash
# Clone the repo
git clone https://github.com/randomness11/probablyprofit.git
cd probablyprofit

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install with dev dependencies
pip install -e ".[dev]"

# Copy environment template
cp .env.example .env
# Edit .env with your API keys
```

## Code Style

We use these tools to maintain consistent code:

```bash
# Format code
black .
isort .

# Check types
mypy probablyprofit/

# Run tests
pytest tests/ -v
```

All PRs must pass these checks.

## Project Structure

```
probablyprofit/
├── agent/          # AI agents (OpenAI, Gemini, Anthropic, Ensemble)
├── api/            # Platform clients (Polymarket, Kalshi)
├── plugins/        # Plugin system for extensibility
├── risk/           # Risk management
├── storage/        # Database persistence
├── backtesting/    # Backtesting engine
├── web/            # Web dashboard
├── examples/       # Example strategy templates
└── tests/          # Unit tests
```

## Adding a New Agent

1. Create `agent/your_agent.py`
2. Inherit from `BaseAgent`
3. Implement `decide(observation)` method
4. Add to `main.py` agent selection

```python
from probablyprofit.agent.base import BaseAgent, Decision

class YourAgent(BaseAgent):
    async def decide(self, observation):
        # Your trading logic here
        return Decision(
            action="buy",
            market_id="...",
            outcome="Yes",
            size=10.0,
            price=0.5,
            reasoning="Why this trade"
        )
```

## Adding a New Strategy

1. Create `examples/your_strategy.txt` with trading instructions
2. Test with: `python main.py --strategy custom --prompt-file examples/your_strategy.txt --dry-run`

## Adding a New Plugin

Use the plugin registry:

```python
from probablyprofit.plugins.registry import registry, PluginType
from probablyprofit.plugins.base import StrategyPlugin

@registry.register("my_strategy", PluginType.STRATEGY)
class MyStrategy(StrategyPlugin):
    def generate_signals(self, markets):
        # Your logic
        return signals
```

## Pull Requests

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes
4. Run tests: `pytest tests/ -v`
5. Run formatters: `black . && isort .`
6. Commit with clear message
7. Push and create PR

## Questions?

Open an issue or start a discussion!
