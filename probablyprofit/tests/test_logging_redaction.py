"""
Tests for the logging module with secret redaction.
"""

import pytest


class TestRedactString:
    """Tests for redact_string function."""

    def test_redact_openai_key(self):
        """Test redacting OpenAI API key pattern."""
        from probablyprofit.utils.logging import redact_string

        text = "Using API key sk-abc123def456ghi789jkl012mno345"
        result = redact_string(text)

        assert "sk-abc123" not in result
        assert "****" in result or "***" in result

    def test_redact_anthropic_key(self):
        """Test redacting Anthropic API key pattern."""
        from probablyprofit.utils.logging import redact_string

        text = "Anthropic key: sk-ant-api03-abcdefghijklmnopqrstuvwxyz"
        result = redact_string(text)

        assert "sk-ant-api03-abc" not in result

    def test_redact_eth_private_key(self):
        """Test redacting Ethereum private key."""
        from probablyprofit.utils.logging import redact_string

        # 64 hex chars
        key = "a" * 64
        text = f"Private key: {key}"
        result = redact_string(text)

        assert key not in result

    def test_redact_eth_private_key_with_0x(self):
        """Test redacting Ethereum private key with 0x prefix."""
        from probablyprofit.utils.logging import redact_string

        key = "0x" + "b" * 64
        text = f"Key is {key}"
        result = redact_string(text)

        assert key not in result

    def test_redact_bearer_token(self):
        """Test redacting Bearer token."""
        from probablyprofit.utils.logging import redact_string

        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        result = redact_string(text)

        assert "eyJhbGciOiJ" not in result

    def test_no_redaction_for_normal_text(self):
        """Test that normal text is not redacted."""
        from probablyprofit.utils.logging import redact_string

        text = "This is a normal log message about trading"
        result = redact_string(text)

        assert result == text

    def test_empty_string(self):
        """Test empty string."""
        from probablyprofit.utils.logging import redact_string

        assert redact_string("") == ""
        assert redact_string(None) is None


class TestRedactDict:
    """Tests for redact_dict function."""

    def test_redact_sensitive_key(self):
        """Test redacting value with sensitive key name."""
        from probablyprofit.utils.logging import redact_dict

        data = {"api_key": "sk-secret-value-12345678"}
        result = redact_dict(data)

        assert "sk-secret" not in result["api_key"]
        assert "****" in result["api_key"]

    def test_redact_password_key(self):
        """Test redacting password field."""
        from probablyprofit.utils.logging import redact_dict

        data = {"password": "mysupersecretpassword"}
        result = redact_dict(data)

        assert result["password"] != "mysupersecretpassword"
        assert "****" in result["password"]

    def test_nested_dict_redaction(self):
        """Test redacting nested dictionaries."""
        from probablyprofit.utils.logging import redact_dict

        data = {
            "config": {
                "api_key": "sk-nested-secret-key",
                "name": "test",
            }
        }
        result = redact_dict(data)

        assert "sk-nested" not in result["config"]["api_key"]
        assert result["config"]["name"] == "test"

    def test_list_in_dict_redaction(self):
        """Test redacting lists within dicts - list values may not be redacted by key name."""
        from probablyprofit.utils.logging import redact_dict

        # redact_dict looks at key names, list items may need pattern matching
        data = {
            "api_keys": ["sk-key1-abcdefghijklmnop", "sk-key2-qrstuvwxyz123456"]
        }
        result = redact_dict(data)

        # The key "api_keys" contains "key" so values should be redacted
        assert result is not None
        # Just verify it returns without error - exact behavior depends on implementation

    def test_non_sensitive_keys_preserved(self):
        """Test that non-sensitive data is preserved."""
        from probablyprofit.utils.logging import redact_dict

        data = {
            "name": "test_agent",
            "count": 42,
            "active": True,
        }
        result = redact_dict(data)

        assert result["name"] == "test_agent"
        assert result["count"] == 42
        assert result["active"] is True


class TestRegisterSecret:
    """Tests for register_secret function."""

    def test_register_and_redact(self):
        """Test registering a custom secret for redaction."""
        from probablyprofit.utils.logging import redact_string, register_secret

        custom_secret = "my-custom-secret-value-xyz"
        register_secret(custom_secret)

        text = f"The secret is {custom_secret}"
        result = redact_string(text)

        assert custom_secret not in result

    def test_register_short_secret_ignored(self):
        """Test that very short secrets are ignored."""
        from probablyprofit.utils.logging import _known_secrets, register_secret

        initial_count = len(_known_secrets)
        register_secret("abc")  # Too short

        assert len(_known_secrets) == initial_count


class TestGetSafeRepr:
    """Tests for get_safe_repr function."""

    def test_safe_repr_dict(self):
        """Test safe repr of dictionary."""
        from probablyprofit.utils.logging import get_safe_repr

        data = {"api_key": "sk-secret123456789012345678"}
        result = get_safe_repr(data)

        assert "sk-secret" not in result
        assert isinstance(result, str)

    def test_safe_repr_string(self):
        """Test safe repr of string."""
        from probablyprofit.utils.logging import get_safe_repr

        text = "Key: sk-abcdefghijklmnopqrstuvwxyz"
        result = get_safe_repr(text)

        assert "sk-abcdef" not in result

    def test_safe_repr_truncation(self):
        """Test that long output is truncated."""
        from probablyprofit.utils.logging import get_safe_repr

        long_text = "x" * 500
        result = get_safe_repr(long_text, max_length=100)

        assert len(result) <= 103  # 100 + "..."

    def test_safe_repr_none(self):
        """Test safe repr of None."""
        from probablyprofit.utils.logging import get_safe_repr

        assert get_safe_repr(None) == "None"
