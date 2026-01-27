"""
Plugin Registry

Central registry for discovering and managing plugins.

SECURITY WARNING:
    Plugin loading executes arbitrary Python code from plugin files.
    This is a significant security risk:

    1. ONLY load plugins from TRUSTED sources
    2. NEVER load plugins from user-provided paths in production
    3. Consider implementing plugin signature verification for production use
    4. Review all plugin code before enabling

    The discover_plugins() method will execute any .py file in the specified
    directory, which could contain malicious code that:
    - Steals credentials or private keys
    - Executes system commands
    - Modifies trading behavior
    - Exfiltrates data

    For production deployments, consider:
    - Using a plugin allowlist
    - Implementing code signing/verification
    - Running plugins in a sandboxed environment
    - Disabling auto-discovery entirely
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Type

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
        self._plugins: Dict[PluginType, Dict[str, PluginInfo]] = {pt: {} for pt in PluginType}
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
                cls, name, plugin_type, version=version, author=author, description=description
            )
            return cls

        return decorator

    def register_plugin(self, cls: Type, name: str, plugin_type: PluginType, **metadata) -> None:
        """Register a plugin class directly."""
        if name in self._plugins[plugin_type]:
            logger.warning(f"Plugin '{name}' already registered, overwriting")

        info = PluginInfo(name=name, plugin_type=plugin_type, cls=cls, **metadata)

        self._plugins[plugin_type][name] = info
        logger.debug(f"Registered plugin: {name} ({plugin_type.value})")

    def get(self, name: str, plugin_type: PluginType) -> Optional[PluginInfo]:
        """Get plugin info by name and type."""
        return self._plugins[plugin_type].get(name)

    def get_all(self, plugin_type: PluginType) -> List[PluginInfo]:
        """Get all plugins of a given type."""
        return list(self._plugins[plugin_type].values())

    def create_instance(self, name: str, plugin_type: PluginType, **kwargs) -> Any:
        """Create an instance of a registered plugin."""
        info = self.get(name, plugin_type)
        if not info:
            raise ValueError(f"Plugin '{name}' not found in {plugin_type.value}")

        instance = info.cls(**kwargs)
        self._instances[name] = instance
        return instance

    def list_plugins(self) -> Dict[str, List[str]]:
        """List all registered plugins by type."""
        return {pt.value: list(plugins.keys()) for pt, plugins in self._plugins.items() if plugins}

    def discover_plugins(self, path: str, trusted: bool = False) -> int:
        """
        Auto-discover plugins from a directory.

        SECURITY WARNING:
            This method executes arbitrary Python code from plugin files.
            Only use with TRUSTED plugin directories. Malicious plugins can:
            - Steal credentials and private keys
            - Execute system commands
            - Modify trading behavior
            - Exfiltrate sensitive data

        Args:
            path: Directory path containing plugin files
            trusted: Must be explicitly set to True to acknowledge security risk

        Returns:
            Number of plugins discovered

        Raises:
            SecurityError: If trusted=False (default) to prevent accidental use
        """
        import importlib.util
        import os

        # SECURITY: Require explicit acknowledgment of security risk
        if not trusted:
            logger.error(
                "SECURITY: Plugin discovery blocked. "
                "Loading plugins executes arbitrary code which is a security risk. "
                "If you trust the plugin source, call discover_plugins(path, trusted=True)"
            )
            raise SecurityError(
                "Plugin discovery requires explicit trust acknowledgment. "
                "Set trusted=True if you trust the plugin source."
            )

        count = 0

        if not os.path.isdir(path):
            logger.warning(f"Plugin directory not found: {path}")
            return 0

        # SECURITY: Log which directory is being loaded for audit trail
        logger.warning(
            f"SECURITY: Loading plugins from {path}. "
            "Ensure this directory contains only trusted code."
        )

        for filename in os.listdir(path):
            if not filename.endswith(".py") or filename.startswith("_"):
                continue

            filepath = os.path.join(path, filename)
            module_name = filename[:-3]

            try:
                logger.debug(f"Loading plugin file: {filepath}")
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


class SecurityError(Exception):
    """Raised when a security constraint is violated."""

    pass
