"""
Plugin Registry

Central registry for discovering and managing plugins.
"""

from typing import Dict, List, Type, Optional, Any
from enum import Enum
from dataclasses import dataclass, field
from loguru import logger


class PluginType(Enum):
    """Types of plugins supported."""
    DATA_SOURCE = "data_source"
    AGENT = "agent"
    STRATEGY = "strategy"
    RISK = "risk"
    OUTPUT = "output"


@dataclass
class PluginInfo:
    """Metadata about a registered plugin."""
    name: str
    plugin_type: PluginType
    cls: Type
    version: str = "1.0.0"
    author: str = "unknown"
    description: str = ""
    config_schema: Dict[str, Any] = field(default_factory=dict)


class PluginRegistry:
    """
    Central registry for all plugins.
    
    Plugins can be registered via:
    1. Decorator: @registry.register("my_plugin", PluginType.STRATEGY)
    2. Direct call: registry.register_plugin(MyPlugin, "my_plugin", PluginType.STRATEGY)
    3. Auto-discovery: registry.discover_plugins("path/to/plugins")
    """
    
    def __init__(self):
        self._plugins: Dict[PluginType, Dict[str, PluginInfo]] = {
            pt: {} for pt in PluginType
        }
        self._instances: Dict[str, Any] = {}
        
    def register(
        self,
        name: str,
        plugin_type: PluginType,
        version: str = "1.0.0",
        author: str = "unknown",
        description: str = "",
    ):
        """
        Decorator to register a plugin class.
        
        Usage:
            @registry.register("my_strategy", PluginType.STRATEGY)
            class MyStrategy(StrategyPlugin):
                ...
        """
        def decorator(cls):
            self.register_plugin(
                cls, name, plugin_type,
                version=version, author=author, description=description
            )
            return cls
        return decorator
    
    def register_plugin(
        self,
        cls: Type,
        name: str,
        plugin_type: PluginType,
        **metadata
    ) -> None:
        """Register a plugin class directly."""
        if name in self._plugins[plugin_type]:
            logger.warning(f"Plugin '{name}' already registered, overwriting")
        
        info = PluginInfo(
            name=name,
            plugin_type=plugin_type,
            cls=cls,
            **metadata
        )
        
        self._plugins[plugin_type][name] = info
        logger.debug(f"Registered plugin: {name} ({plugin_type.value})")
    
    def get(self, name: str, plugin_type: PluginType) -> Optional[PluginInfo]:
        """Get plugin info by name and type."""
        return self._plugins[plugin_type].get(name)
    
    def get_all(self, plugin_type: PluginType) -> List[PluginInfo]:
        """Get all plugins of a given type."""
        return list(self._plugins[plugin_type].values())
    
    def create_instance(
        self,
        name: str,
        plugin_type: PluginType,
        **kwargs
    ) -> Any:
        """Create an instance of a registered plugin."""
        info = self.get(name, plugin_type)
        if not info:
            raise ValueError(f"Plugin '{name}' not found in {plugin_type.value}")
        
        instance = info.cls(**kwargs)
        self._instances[name] = instance
        return instance
    
    def list_plugins(self) -> Dict[str, List[str]]:
        """List all registered plugins by type."""
        return {
            pt.value: list(plugins.keys())
            for pt, plugins in self._plugins.items()
            if plugins
        }
    
    def discover_plugins(self, path: str) -> int:
        """
        Auto-discover plugins from a directory.
        
        Looks for Python files with classes that inherit from BasePlugin.
        Returns number of plugins discovered.
        """
        import importlib.util
        import os
        
        count = 0
        
        if not os.path.isdir(path):
            logger.warning(f"Plugin directory not found: {path}")
            return 0
        
        for filename in os.listdir(path):
            if not filename.endswith('.py') or filename.startswith('_'):
                continue
            
            filepath = os.path.join(path, filename)
            module_name = filename[:-3]
            
            try:
                spec = importlib.util.spec_from_file_location(module_name, filepath)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    # Plugins self-register via decorator
                    # Count what was registered from this module
                    for pt in PluginType:
                        for info in self._plugins[pt].values():
                            if info.cls.__module__ == module_name:
                                count += 1
                                
            except Exception as e:
                logger.warning(f"Failed to load plugin from {filename}: {e}")
        
        logger.info(f"Discovered {count} plugins from {path}")
        return count
