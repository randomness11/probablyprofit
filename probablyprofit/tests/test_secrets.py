"""
Tests for the secrets management module.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestSecretsManager:
    """Tests for SecretsManager class."""

    def test_get_from_environment(self):
        """Test that environment variables take priority."""
        from probablyprofit.utils.secrets import SecretsManager

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-env-key"}):
            manager = SecretsManager()
            result = manager.get("openai_api_key")
            assert result == "sk-test-env-key"

    def test_get_missing_secret_returns_none(self):
        """Test that missing secrets return None."""
        from probablyprofit.utils.secrets import SecretsManager

        # Clear any env vars
        with patch.dict(os.environ, {}, clear=True):
            manager = SecretsManager()
            manager._cache.clear()
            result = manager.get("nonexistent_key")
            assert result is None

    def test_set_and_get_from_cache(self):
        """Test setting and getting from in-memory cache."""
        from probablyprofit.utils.secrets import SecretsManager

        manager = SecretsManager()
        manager._keyring_available = False  # Disable keyring
        manager._crypto_available = False  # Disable crypto

        # Set should update cache
        manager._cache["test_key"] = "test_value"

        result = manager.get("test_key")
        assert result == "test_value"

    def test_clear_cache(self):
        """Test clearing the cache."""
        from probablyprofit.utils.secrets import SecretsManager

        manager = SecretsManager()
        manager._cache["key1"] = "value1"
        manager._cache["key2"] = "value2"

        manager.clear_cache()

        assert len(manager._cache) == 0

    def test_backend_info(self):
        """Test backend info property."""
        from probablyprofit.utils.secrets import SecretsManager

        manager = SecretsManager()
        info = manager.backend_info

        assert "keyring_available" in info
        assert "encryption_available" in info
        assert isinstance(info["keyring_available"], bool)
        assert isinstance(info["encryption_available"], bool)


class TestRedactSecret:
    """Tests for redact_secret function."""

    def test_redact_long_secret(self):
        """Test redacting a long secret."""
        from probablyprofit.utils.secrets import redact_secret

        result = redact_secret("sk-abcdefghijklmnop")
        # 19 chars - 4 show_chars = 15 asterisks + last 4 chars
        assert result == "***************mnop"
        assert len(result) == len("sk-abcdefghijklmnop")

    def test_redact_short_secret(self):
        """Test redacting a short secret."""
        from probablyprofit.utils.secrets import redact_secret

        result = redact_secret("abc")
        assert result == "***"

    def test_redact_empty_secret(self):
        """Test redacting empty string."""
        from probablyprofit.utils.secrets import redact_secret

        result = redact_secret("")
        assert result == ""

    def test_redact_with_custom_show_chars(self):
        """Test redacting with custom visible characters."""
        from probablyprofit.utils.secrets import redact_secret

        # "sk-abcdefghij" = 13 chars, show 6 = 7 asterisks + last 6 chars
        result = redact_secret("sk-abcdefghij", show_chars=6)
        assert result == "*******efghij"


class TestGetSecret:
    """Tests for convenience functions."""

    def test_get_secret_convenience(self):
        """Test get_secret convenience function."""
        from probablyprofit.utils.secrets import get_secret

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}):
            result = get_secret("anthropic_api_key")
            assert result == "sk-ant-test"

    def test_set_secret_convenience(self):
        """Test set_secret convenience function."""
        from probablyprofit.utils.secrets import get_secrets_manager, set_secret

        # This will try to set in cache at minimum
        manager = get_secrets_manager()
        manager._keyring_available = False
        manager._crypto_available = False

        result = set_secret("test_secret", "test_value")
        # Without backends, it returns False but cache is updated
        assert manager._cache.get("test_secret") == "test_value"
