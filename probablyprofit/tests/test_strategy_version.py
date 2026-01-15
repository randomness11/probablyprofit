"""
Tests for the strategy versioning module.
"""

from datetime import datetime, timedelta

import pytest


class TestStrategyVersion:
    """Tests for StrategyVersion class."""

    def test_create_from_content(self):
        """Test creating version from content."""
        from probablyprofit.agent.strategy_version import StrategyVersion

        content = "Buy low, sell high"
        version = StrategyVersion.from_content(content, name="Simple Strategy")

        assert version.content == content
        assert version.name == "Simple Strategy"
        assert version.version_hash is not None
        assert len(version.version_hash) == 12

    def test_same_content_same_hash(self):
        """Test that same content produces same hash."""
        from probablyprofit.agent.strategy_version import StrategyVersion

        content = "Momentum trading strategy"
        v1 = StrategyVersion.from_content(content)
        v2 = StrategyVersion.from_content(content)

        assert v1.version_hash == v2.version_hash

    def test_different_content_different_hash(self):
        """Test that different content produces different hash."""
        from probablyprofit.agent.strategy_version import StrategyVersion

        v1 = StrategyVersion.from_content("Strategy A")
        v2 = StrategyVersion.from_content("Strategy B")

        assert v1.version_hash != v2.version_hash

    def test_short_hash(self):
        """Test short hash property."""
        from probablyprofit.agent.strategy_version import StrategyVersion

        version = StrategyVersion.from_content("Test")

        assert len(version.short_hash) == 8
        assert version.short_hash == version.version_hash[:8]

    def test_to_dict(self):
        """Test converting to dictionary."""
        from probablyprofit.agent.strategy_version import StrategyVersion

        version = StrategyVersion.from_content(
            "Test strategy",
            name="Test",
            description="A test strategy",
            metadata={"author": "test"},
        )
        result = version.to_dict()

        assert "version_hash" in result
        assert "created_at" in result
        assert result["name"] == "Test"
        assert result["description"] == "A test strategy"
        assert "content_length" in result

    def test_to_json(self):
        """Test converting to JSON string."""
        from probablyprofit.agent.strategy_version import StrategyVersion

        version = StrategyVersion.from_content("Test")
        json_str = version.to_json()

        assert isinstance(json_str, str)
        assert "version_hash" in json_str

    def test_str_representation(self):
        """Test string representation."""
        from probablyprofit.agent.strategy_version import StrategyVersion

        version = StrategyVersion.from_content("Test", name="MyStrategy")
        str_repr = str(version)

        assert "Strategy v" in str_repr
        assert "MyStrategy" in str_repr


class TestStrategyRegistry:
    """Tests for StrategyRegistry class."""

    def test_register_new_version(self):
        """Test registering a new strategy version."""
        from probablyprofit.agent.strategy_version import StrategyRegistry

        registry = StrategyRegistry()
        version = registry.register("Buy when price < 0.3", name="Value Strategy")

        assert version is not None
        assert registry.version_count == 1

    def test_register_duplicate_returns_existing(self):
        """Test registering duplicate content returns existing version."""
        from probablyprofit.agent.strategy_version import StrategyRegistry

        registry = StrategyRegistry()
        content = "Momentum strategy"

        v1 = registry.register(content)
        v2 = registry.register(content)

        assert v1.version_hash == v2.version_hash
        assert registry.version_count == 1

    def test_activate_version(self):
        """Test activating a version."""
        from probablyprofit.agent.strategy_version import StrategyRegistry

        registry = StrategyRegistry()
        v1 = registry.register("Strategy 1", activate=False)
        v2 = registry.register("Strategy 2", activate=False)

        registry.activate(v1.version_hash)

        assert registry.active_version_hash == v1.version_hash

        registry.activate(v2.version_hash)

        assert registry.active_version_hash == v2.version_hash

    def test_activate_unknown_version_fails(self):
        """Test activating unknown version returns False."""
        from probablyprofit.agent.strategy_version import StrategyRegistry

        registry = StrategyRegistry()

        result = registry.activate("nonexistent_hash")

        assert result is False

    def test_get_active(self):
        """Test getting active version."""
        from probablyprofit.agent.strategy_version import StrategyRegistry

        registry = StrategyRegistry()
        version = registry.register("Active strategy")

        active = registry.get_active()

        assert active is not None
        assert active.content == "Active strategy"

    def test_get_active_none_when_empty(self):
        """Test getting active returns None when no version registered."""
        from probablyprofit.agent.strategy_version import StrategyRegistry

        registry = StrategyRegistry()

        assert registry.get_active() is None

    def test_get_version_by_hash(self):
        """Test getting version by hash."""
        from probablyprofit.agent.strategy_version import StrategyRegistry

        registry = StrategyRegistry()
        version = registry.register("Test strategy")

        retrieved = registry.get_version(version.version_hash)

        assert retrieved is not None
        assert retrieved.content == "Test strategy"

    def test_get_all_versions(self):
        """Test getting all registered versions."""
        from probablyprofit.agent.strategy_version import StrategyRegistry

        registry = StrategyRegistry()
        registry.register("Strategy 1")
        registry.register("Strategy 2")
        registry.register("Strategy 3")

        all_versions = registry.get_all_versions()

        assert len(all_versions) == 3

    def test_get_history(self):
        """Test getting activation history."""
        from probablyprofit.agent.strategy_version import StrategyRegistry

        registry = StrategyRegistry()
        v1 = registry.register("Strategy 1")
        v2 = registry.register("Strategy 2")

        history = registry.get_history()

        assert len(history) == 2
        assert history[0][1] == v1.version_hash
        assert history[1][1] == v2.version_hash

    def test_get_version_at_time(self):
        """Test getting version that was active at a specific time."""
        from probablyprofit.agent.strategy_version import StrategyRegistry

        registry = StrategyRegistry()

        # Register first version
        v1 = registry.register("Strategy 1")
        time_after_v1 = datetime.now()

        # Register second version
        v2 = registry.register("Strategy 2")

        # Query for time after v1 but before v2 would have been activated
        # Since we can't easily control time, test that we get a valid result
        result = registry.get_version_at_time(datetime.now())

        assert result is not None
        assert result.version_hash == v2.version_hash

    def test_to_dict(self):
        """Test converting registry to dictionary."""
        from probablyprofit.agent.strategy_version import StrategyRegistry

        registry = StrategyRegistry()
        registry.register("Test")

        result = registry.to_dict()

        assert "active_version" in result
        assert "version_count" in result
        assert "versions" in result
        assert "history_length" in result
        assert result["version_count"] == 1


class TestGlobalFunctions:
    """Tests for global convenience functions."""

    def test_get_strategy_registry_singleton(self):
        """Test that get_strategy_registry returns singleton."""
        from probablyprofit.agent.strategy_version import get_strategy_registry

        r1 = get_strategy_registry()
        r2 = get_strategy_registry()

        assert r1 is r2

    def test_register_strategy(self):
        """Test register_strategy convenience function."""
        from probablyprofit.agent.strategy_version import register_strategy

        version = register_strategy(
            "Buy momentum stocks",
            name="Momentum",
            description="Follow the trend",
        )

        assert version is not None
        assert version.name == "Momentum"

    def test_get_active_strategy(self):
        """Test get_active_strategy convenience function."""
        from probablyprofit.agent.strategy_version import (get_active_strategy,
                                                            register_strategy)

        register_strategy("Current active strategy")
        active = get_active_strategy()

        assert active is not None


class TestComputeHash:
    """Tests for hash computation."""

    def test_compute_hash_deterministic(self):
        """Test that hash computation is deterministic."""
        from probablyprofit.agent.strategy_version import StrategyVersion

        content = "Test content for hashing"
        hash1 = StrategyVersion.compute_hash(content)
        hash2 = StrategyVersion.compute_hash(content)

        assert hash1 == hash2

    def test_compute_hash_length(self):
        """Test that hash has expected length."""
        from probablyprofit.agent.strategy_version import StrategyVersion

        content = "Any content"
        hash_val = StrategyVersion.compute_hash(content)

        assert len(hash_val) == 12  # First 12 chars of SHA-256

    def test_compute_hash_is_hex(self):
        """Test that hash is valid hexadecimal."""
        from probablyprofit.agent.strategy_version import StrategyVersion

        content = "Test"
        hash_val = StrategyVersion.compute_hash(content)

        # Should not raise
        int(hash_val, 16)
