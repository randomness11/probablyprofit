"""
probablyprofit Plugin System

Extensible plugin architecture for adding custom:
- Data sources
- Agents
- Strategies
- Risk rules
- Output handlers
"""

from probablyprofit.plugins.registry import PluginRegistry, PluginType
from probablyprofit.plugins.base import (
    BasePlugin,
    DataSourcePlugin,
    AgentPlugin,
    StrategyPlugin,
    RiskPlugin,
    OutputPlugin,
)
from probablyprofit.plugins.hooks import HookManager, Hook

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
