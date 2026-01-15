"""
Tests for configuration classes and validation.
"""

import os
from unittest.mock import patch

import pytest


class TestConfig:
    """Tests for main Config class."""

    def test_default_values(self):
        """Test Config has sensible defaults."""
        from probablyprofit.config import Config

        config = Config()

        assert config.dry_run is True  # Safe default
        assert config.interval >= 30  # Reasonable interval
        assert config.platform in ["polymarket", "kalshi"]

    def test_get_available_agents_empty(self):
        """Test getting available agents when none configured."""
        from probablyprofit.config import Config

        config = Config()
        config.openai_api_key = None
        config.anthropic_api_key = None
        config.google_api_key = None

        agents = config.get_available_agents()
        assert agents == []

    def test_get_available_agents_with_keys(self):
        """Test getting available agents when configured."""
        from probablyprofit.config import Config

        config = Config()
        config.openai_api_key = "sk-test"
        config.anthropic_api_key = "sk-ant-test"

        agents = config.get_available_agents()
        assert "openai" in agents
        assert "anthropic" in agents

    def test_get_best_agent_preference(self):
        """Test agent preference order."""
        from probablyprofit.config import Config

        config = Config()
        config.openai_api_key = "sk-test"
        config.anthropic_api_key = "sk-ant-test"
        config.google_api_key = "google-test"
        config.preferred_agent = "auto"

        # Anthropic should be preferred
        best = config.get_best_agent()
        assert best == "anthropic"

    def test_get_best_agent_custom_preference(self):
        """Test custom agent preference."""
        from probablyprofit.config import Config

        config = Config()
        config.openai_api_key = "sk-test"
        config.anthropic_api_key = "sk-ant-test"
        config.preferred_agent = "openai"

        best = config.get_best_agent()
        assert best == "openai"

    def test_has_wallet(self):
        """Test wallet configuration check."""
        from probablyprofit.config import Config

        config = Config()
        assert config.has_wallet() is False

        config.private_key = "0x" + "a" * 64
        assert config.has_wallet() is True

    def test_to_dict(self):
        """Test converting config to dictionary."""
        from probablyprofit.config import Config

        config = Config()
        result = config.to_dict()

        assert isinstance(result, dict)
        assert "ai" in result
        assert "trading" in result


class TestStrategyConfig:
    """Tests for StrategyConfig dataclass."""

    def test_default_values(self):
        """Test default strategy config values."""
        from probablyprofit.config import StrategyConfig

        config = StrategyConfig()

        assert config.min_liquidity >= 0
        assert 0 <= config.extreme_threshold <= 1
        assert 0 <= config.value_lower_bound < config.value_upper_bound <= 1

    def test_custom_values(self):
        """Test custom strategy config values."""
        from probablyprofit.config import StrategyConfig

        config = StrategyConfig(
            min_liquidity=5000.0,
            extreme_threshold=0.9,
        )

        assert config.min_liquidity == 5000.0
        assert config.extreme_threshold == 0.9


class TestArbitrageConfig:
    """Tests for ArbitrageConfig dataclass."""

    def test_default_values(self):
        """Test default arbitrage config values."""
        from probablyprofit.config import ArbitrageConfig

        config = ArbitrageConfig()

        assert config.min_profit_pct >= 0
        assert config.polymarket_fee >= 0
        assert config.kalshi_fee >= 0
        assert 0 <= config.min_match_similarity <= 1

    def test_custom_values(self):
        """Test custom arbitrage config values."""
        from probablyprofit.config import ArbitrageConfig

        config = ArbitrageConfig(
            min_profit_pct=0.05,
            min_match_similarity=0.8,
        )

        assert config.min_profit_pct == 0.05
        assert config.min_match_similarity == 0.8


class TestRiskConfig:
    """Tests for RiskConfig dataclass."""

    def test_default_values(self):
        """Test default risk config values."""
        from probablyprofit.config import RiskConfig

        config = RiskConfig()

        assert 0 < config.max_position_pct <= 1
        assert config.max_single_trade > 0
        assert 0 < config.max_daily_loss_pct <= 1

    def test_kelly_fraction(self):
        """Test Kelly fraction is reasonable."""
        from probablyprofit.config import RiskConfig

        config = RiskConfig()

        # Kelly fraction should be less than 1 (full Kelly)
        assert 0 < config.kelly_fraction <= 1


class TestAPIConfig:
    """Tests for APIConfig dataclass."""

    def test_default_timeouts(self):
        """Test default timeout values."""
        from probablyprofit.config import APIConfig

        config = APIConfig()

        assert config.http_timeout > 0
        assert config.websocket_timeout > 0
        assert config.websocket_timeout >= config.http_timeout

    def test_rate_limiting(self):
        """Test rate limiting configuration."""
        from probablyprofit.config import APIConfig

        config = APIConfig()

        assert config.polymarket_rate_limit_calls > 0
        assert config.polymarket_rate_limit_period > 0


class TestAgentConfig:
    """Tests for AgentConfig dataclass."""

    def test_default_values(self):
        """Test default agent config values."""
        from probablyprofit.config import AgentConfig

        config = AgentConfig()

        assert config.default_loop_interval > 0
        assert config.max_consecutive_errors > 0
        assert config.memory_max_observations > 0

    def test_backoff_values(self):
        """Test backoff configuration."""
        from probablyprofit.config import AgentConfig

        config = AgentConfig()

        assert config.base_backoff < config.max_backoff


class TestGetConfig:
    """Tests for get_config function."""

    def test_get_config_returns_config(self):
        """Test that get_config returns a Config object."""
        from probablyprofit.config import Config, get_config

        config = get_config()

        assert isinstance(config, Config)

    def test_get_config_singleton(self):
        """Test that get_config returns same instance."""
        from probablyprofit.config import get_config

        config1 = get_config()
        config2 = get_config()

        # Should be same instance (or at least equal)
        assert config1 is config2 or config1.to_dict() == config2.to_dict()
