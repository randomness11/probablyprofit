"""
Configuration Management for ProbablyProfit

Handles loading, saving, and validating configuration from multiple sources:
1. ~/.probablyprofit/config.yaml (user config)
2. .env file (local project config)
3. Environment variables (runtime overrides)
"""

import os
import yaml
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from dotenv import load_dotenv


# Config directory
CONFIG_DIR = Path.home() / ".probablyprofit"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.yaml"


@dataclass
class AIProvider:
    """Configuration for an AI provider."""
    name: str
    api_key: Optional[str] = None
    model: str = ""
    available: bool = False


@dataclass
class WalletConfig:
    """Wallet configuration."""
    private_key: Optional[str] = None
    platform: str = "polymarket"  # polymarket or kalshi


@dataclass
class Config:
    """Main configuration object."""
    # AI Providers
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o"
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-sonnet-4-5-20250929"
    google_api_key: Optional[str] = None
    google_model: str = "gemini-2.0-flash"

    # Wallet
    private_key: Optional[str] = None
    platform: str = "polymarket"

    # Trading
    initial_capital: float = 1000.0
    dry_run: bool = True  # Default to safe mode
    interval: int = 60

    # Intelligence
    perplexity_api_key: Optional[str] = None
    twitter_bearer_token: Optional[str] = None

    # Risk
    max_position_size: float = 50.0
    max_daily_loss: float = 100.0

    # State
    is_configured: bool = False
    preferred_agent: str = "auto"  # auto, openai, anthropic, google

    def get_available_agents(self) -> List[str]:
        """Get list of configured AI providers."""
        agents = []
        if self.openai_api_key:
            agents.append("openai")
        if self.anthropic_api_key:
            agents.append("anthropic")
        if self.google_api_key:
            agents.append("google")
        return agents

    def get_best_agent(self) -> Optional[str]:
        """Get the best available agent (user preference or first available)."""
        available = self.get_available_agents()
        if not available:
            return None
        if self.preferred_agent != "auto" and self.preferred_agent in available:
            return self.preferred_agent
        # Preference order: anthropic > openai > google
        for agent in ["anthropic", "openai", "google"]:
            if agent in available:
                return agent
        return available[0] if available else None

    def get_api_key_for_agent(self, agent: str) -> Optional[str]:
        """Get API key for a specific agent."""
        mapping = {
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
            "google": self.google_api_key,
        }
        return mapping.get(agent)

    def get_model_for_agent(self, agent: str) -> str:
        """Get model name for a specific agent."""
        mapping = {
            "openai": self.openai_model,
            "anthropic": self.anthropic_model,
            "google": self.google_model,
        }
        return mapping.get(agent, "")

    def has_wallet(self) -> bool:
        """Check if wallet is configured."""
        return bool(self.private_key)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for saving."""
        return {
            "ai": {
                "preferred_agent": self.preferred_agent,
                "openai_model": self.openai_model,
                "anthropic_model": self.anthropic_model,
                "google_model": self.google_model,
            },
            "trading": {
                "platform": self.platform,
                "initial_capital": self.initial_capital,
                "dry_run": self.dry_run,
                "interval": self.interval,
            },
            "risk": {
                "max_position_size": self.max_position_size,
                "max_daily_loss": self.max_daily_loss,
            },
        }

    def credentials_to_dict(self) -> Dict[str, Any]:
        """Get credentials as dictionary (stored separately for security)."""
        creds = {}
        if self.openai_api_key:
            creds["openai_api_key"] = self.openai_api_key
        if self.anthropic_api_key:
            creds["anthropic_api_key"] = self.anthropic_api_key
        if self.google_api_key:
            creds["google_api_key"] = self.google_api_key
        if self.private_key:
            creds["private_key"] = self.private_key
        if self.perplexity_api_key:
            creds["perplexity_api_key"] = self.perplexity_api_key
        if self.twitter_bearer_token:
            creds["twitter_bearer_token"] = self.twitter_bearer_token
        return creds


def ensure_config_dir() -> Path:
    """Ensure config directory exists."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return CONFIG_DIR


def load_config() -> Config:
    """
    Load configuration from all sources.

    Priority (highest to lowest):
    1. Environment variables
    2. .env file in current directory
    3. ~/.probablyprofit/credentials.yaml
    4. ~/.probablyprofit/config.yaml
    """
    config = Config()

    # Load from user config files
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                data = yaml.safe_load(f) or {}

            # AI settings
            ai = data.get("ai", {})
            config.preferred_agent = ai.get("preferred_agent", "auto")
            config.openai_model = ai.get("openai_model", config.openai_model)
            config.anthropic_model = ai.get("anthropic_model", config.anthropic_model)
            config.google_model = ai.get("google_model", config.google_model)

            # Trading settings
            trading = data.get("trading", {})
            config.platform = trading.get("platform", config.platform)
            config.initial_capital = trading.get("initial_capital", config.initial_capital)
            config.dry_run = trading.get("dry_run", config.dry_run)
            config.interval = trading.get("interval", config.interval)

            # Risk settings
            risk = data.get("risk", {})
            config.max_position_size = risk.get("max_position_size", config.max_position_size)
            config.max_daily_loss = risk.get("max_daily_loss", config.max_daily_loss)
        except Exception:
            pass

    # Load credentials from secure file
    if CREDENTIALS_FILE.exists():
        try:
            with open(CREDENTIALS_FILE) as f:
                creds = yaml.safe_load(f) or {}

            config.openai_api_key = creds.get("openai_api_key")
            config.anthropic_api_key = creds.get("anthropic_api_key")
            config.google_api_key = creds.get("google_api_key")
            config.private_key = creds.get("private_key")
            config.perplexity_api_key = creds.get("perplexity_api_key")
            config.twitter_bearer_token = creds.get("twitter_bearer_token")
        except Exception:
            pass

    # Load from .env file (overrides config files)
    load_dotenv()

    # Environment variables override everything
    config.openai_api_key = os.getenv("OPENAI_API_KEY", config.openai_api_key)
    config.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", config.anthropic_api_key)
    config.google_api_key = os.getenv("GOOGLE_API_KEY", config.google_api_key)
    config.private_key = os.getenv("PRIVATE_KEY", config.private_key)
    config.perplexity_api_key = os.getenv("PERPLEXITY_API_KEY", config.perplexity_api_key)
    config.twitter_bearer_token = os.getenv("TWITTER_BEARER_TOKEN", config.twitter_bearer_token)

    if os.getenv("INITIAL_CAPITAL"):
        config.initial_capital = float(os.getenv("INITIAL_CAPITAL"))
    if os.getenv("PLATFORM"):
        config.platform = os.getenv("PLATFORM")

    # Determine if configured
    config.is_configured = len(config.get_available_agents()) > 0

    return config


def save_config(config: Config) -> None:
    """Save configuration to user config files."""
    ensure_config_dir()

    # Save non-sensitive config
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(config.to_dict(), f, default_flow_style=False)

    # Save credentials with restricted permissions
    creds = config.credentials_to_dict()
    if creds:
        with open(CREDENTIALS_FILE, "w") as f:
            yaml.dump(creds, f, default_flow_style=False)
        # Restrict permissions on credentials file
        os.chmod(CREDENTIALS_FILE, 0o600)


def validate_api_key(provider: str, key: str) -> bool:
    """
    Validate an API key by making a simple request.
    Returns True if valid, False otherwise.
    """
    if not key:
        return False

    try:
        if provider == "openai":
            import openai
            client = openai.OpenAI(api_key=key)
            # Simple models list call to validate
            client.models.list()
            return True

        elif provider == "anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=key)
            # Count tokens is a lightweight validation call
            client.count_tokens("test")
            return True

        elif provider == "google":
            import google.generativeai as genai
            genai.configure(api_key=key)
            # List models to validate
            list(genai.list_models())
            return True

    except Exception:
        return False

    return False


def get_quick_status() -> Dict[str, Any]:
    """Get a quick status summary of the configuration."""
    config = load_config()

    return {
        "configured": config.is_configured,
        "agents": config.get_available_agents(),
        "best_agent": config.get_best_agent(),
        "wallet": config.has_wallet(),
        "platform": config.platform,
        "dry_run": config.dry_run,
    }
