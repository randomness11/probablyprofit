"""
probablyprofit Plugin System

Extensible plugin architecture for adding custom:
- Data sources
- Agents
- Strategies
- Risk rules
- Output handlers
"""

from probablyprofit.plugins.base import (
    AgentPlugin,
    BasePlugin,
    DataSourcePlugin,
    OutputPlugin,
    RiskPlugin,
    StrategyPlugin,
)
from probablyprofit.plugins.hooks import Hook, HookManager
from probablyprofit.plugins.registry import PluginRegistry, PluginType

# Global registry instance
registry = PluginRegistry()

__all__ = [
    "registry",
    "PluginRegistry",
    "PluginType",
    "BasePlugin",
    "DataSourcePlugin",
    "AgentPlugin",
    "StrategyPlugin",
    "RiskPlugin",
    "OutputPlugin",
    "HookManager",
    "Hook",
]
