"""
Tests for the plugin system.
"""
import pytest
from probablyprofit.plugins.registry import PluginRegistry, PluginType, PluginInfo
from probablyprofit.plugins.base import (
    BasePlugin,
    DataSourcePlugin,
    StrategyPlugin,
    OutputPlugin,
    PluginConfig,
)


class TestPluginConfig:
    def test_default_config(self):
        config = PluginConfig()
        assert config.enabled is True
        assert config.priority == 0
        assert config.options == {}

    def test_custom_config(self):
        config = PluginConfig(
            enabled=False,
            priority=10,
            options={"key": "value"}
        )
        assert config.enabled is False
        assert config.priority == 10
        assert config.options["key"] == "value"


class TestPluginRegistry:
    def test_register_plugin(self):
        registry = PluginRegistry()
        
        class TestStrategy(StrategyPlugin):
            def get_prompt(self): return "test"
            def filter_markets(self, markets): return markets
        
        registry.register_plugin(
            TestStrategy,
            "test_strategy",
            PluginType.STRATEGY,
            version="1.0.0"
        )
        
        info = registry.get("test_strategy", PluginType.STRATEGY)
        assert info is not None
        assert info.name == "test_strategy"
        assert info.version == "1.0.0"

    def test_register_decorator(self):
        registry = PluginRegistry()
        
        @registry.register("decorated_plugin", PluginType.OUTPUT)
        class DecoratedOutput(OutputPlugin):
            async def send(self, event_type, data): pass
        
        info = registry.get("decorated_plugin", PluginType.OUTPUT)
        assert info is not None
        assert info.cls == DecoratedOutput

    def test_get_all_plugins(self):
        registry = PluginRegistry()
        
        class Strategy1(StrategyPlugin):
            def get_prompt(self): return "1"
            def filter_markets(self, m): return m
            
        class Strategy2(StrategyPlugin):
            def get_prompt(self): return "2"
            def filter_markets(self, m): return m
        
        registry.register_plugin(Strategy1, "s1", PluginType.STRATEGY)
        registry.register_plugin(Strategy2, "s2", PluginType.STRATEGY)
        
        strategies = registry.get_all(PluginType.STRATEGY)
        assert len(strategies) == 2

    def test_create_instance(self):
        registry = PluginRegistry()
        
        class TestOutput(OutputPlugin):
            def __init__(self, name="default"):
                super().__init__()
                self.name = name
            async def send(self, event_type, data): pass
        
        registry.register_plugin(TestOutput, "test_output", PluginType.OUTPUT)
        
        instance = registry.create_instance(
            "test_output",
            PluginType.OUTPUT,
            name="custom"
        )
        assert instance.name == "custom"

    def test_list_plugins(self):
        registry = PluginRegistry()
        
        class TestData(DataSourcePlugin):
            async def fetch(self, query): return {}
        
        registry.register_plugin(TestData, "test_data", PluginType.DATA_SOURCE)
        
        listed = registry.list_plugins()
        assert "data_source" in listed
        assert "test_data" in listed["data_source"]


class TestBasePlugin:
    @pytest.mark.asyncio
    async def test_initialize_and_cleanup(self):
        class TestPlugin(BasePlugin):
            pass
        
        plugin = TestPlugin()
        assert not plugin.is_initialized
        
        await plugin.initialize()
        assert plugin.is_initialized
        
        await plugin.cleanup()
        assert not plugin.is_initialized


class TestDataSourcePlugin:
    @pytest.mark.asyncio
    async def test_fetch_batch(self):
        class TestDataSource(DataSourcePlugin):
            async def fetch(self, query):
                return {"query": query}
        
        source = TestDataSource()
        results = await source.fetch_batch(["a", "b", "c"])
        
        assert len(results) == 3
        assert results[0]["query"] == "a"
        assert results[2]["query"] == "c"
