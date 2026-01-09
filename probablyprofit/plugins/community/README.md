# Community Plugins

This folder is for community-contributed plugins. Drop your custom plugins here!

## How to Create a Plugin

1. Create a Python file in this directory
2. Import the registry and base classes
3. Use the `@registry.register()` decorator

### Example: Custom Data Source

```python
from probablyprofit.plugins import registry, PluginType
from probablyprofit.plugins.base import DataSourcePlugin

@registry.register("my_data_source", PluginType.DATA_SOURCE)
class MyDataSource(DataSourcePlugin):
    async def fetch(self, query: str):
        # Your custom data fetching logic
        return {"data": "your_data"}
```

### Example: Custom Strategy

```python
from probablyprofit.plugins import registry, PluginType
from probablyprofit.plugins.base import StrategyPlugin

@registry.register("my_strategy", PluginType.STRATEGY)
class MyStrategy(StrategyPlugin):
    def get_prompt(self):
        return "Your trading instructions here..."
    
    def filter_markets(self, markets):
        return [m for m in markets if m.volume > 10000]
```

### Example: Notification Plugin

```python
from probablyprofit.plugins import registry, PluginType
from probablyprofit.plugins.base import OutputPlugin

@registry.register("telegram_alerts", PluginType.OUTPUT)
class TelegramAlerts(OutputPlugin):
    async def send(self, event_type: str, data: dict):
        # Send to Telegram bot
        pass
```

## Plugin Types

| Type | Base Class | Purpose |
|------|------------|---------|
| `DATA_SOURCE` | `DataSourcePlugin` | Custom data feeds |
| `STRATEGY` | `StrategyPlugin` | Trading strategies |
| `AGENT` | `AgentPlugin` | Custom AI agents |
| `RISK` | `RiskPlugin` | Risk rules |
| `OUTPUT` | `OutputPlugin` | Notifications/logging |
