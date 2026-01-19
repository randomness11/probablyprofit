"""
Configuration Management for ProbablyProfit

Handles loading, saving, and validating configuration from multiple sources:
1. ~/.probablyprofit/config.yaml (user config)
2. .env file (local project config)
3. Environment variables (runtime overrides)
4. Secure secrets storage (keyring/encrypted file)
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from dotenv import load_dotenv
from loguru import logger

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
    platform: str = "polymarket"


@dataclass
class APIConfig:
    """API and network configuration."""

    # Timeouts (seconds)
    http_timeout: float = 30.0
    websocket_timeout: float = 60.0

    # Rate limiting
    polymarket_rate_limit_calls: int = 8
    polymarket_rate_limit_period: float = 1.0

    # Circuit breaker
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: float = 60.0

    # Retry logic
    retry_max_attempts: int = 3
    retry_base_delay: float = 2.0
    retry_max_delay: float = 30.0

    # Cache settings
    market_cache_ttl: float = 60.0
    market_cache_max_size: int = 1000
    price_cache_ttl: float = 10.0
    positions_cache_max_size: int = 200


@dataclass
class AgentConfig:
    """Agent loop configuration."""

    # Loop settings
    default_loop_interval: int = 60
    max_consecutive_errors: int = 10
    base_backoff: float = 5.0
    max_backoff: float = 300.0

    # Memory limits
    memory_max_observations: int = 100
    memory_max_decisions: int = 100
    memory_max_trades: int = 100

    # Checkpointing
    checkpoint_interval: int = 5  # loops
    risk_save_interval: int = 3  # loops (reduced from 10 for production safety)


@dataclass
class RiskConfig:
    """Risk management configuration."""

    # Position limits
    max_position_pct: float = 0.10
    max_single_trade: float = 50.0
    max_daily_loss_pct: float = 0.20
    max_total_exposure_pct: float = 0.50

    # Drawdown limits
    max_drawdown_pct: float = 0.30  # Stop trading if 30% down from peak

    # Sizing
    kelly_fraction: float = 0.25
    min_confidence_to_trade: float = 0.6

    # Stop loss / Take profit
    default_stop_loss_pct: float = 0.20
    default_take_profit_pct: float = 0.50


@dataclass
class TelegramConfig:
    """Telegram alerting configuration."""

    bot_token: Optional[str] = None
    chat_id: Optional[str] = None
    alert_levels: List[str] = field(default_factory=lambda: ["WARNING", "CRITICAL"])
    rate_limit_per_minute: int = 30

    def is_configured(self) -> bool:
        """Check if Telegram is properly configured."""
        return bool(self.bot_token and self.chat_id)


@dataclass
class StrategyConfig:
    """Strategy-specific configuration."""

    # Liquidity strategy
    min_liquidity: float = 1000.0

    # Contrarian strategy
    extreme_threshold: float = 0.85  # Price considered extreme (buy/sell signal)

    # Value strategy
    value_lower_bound: float = 0.30  # Min price for "value" plays
    value_upper_bound: float = 0.70  # Max price for "value" plays

    # Momentum
    momentum_lookback_hours: int = 24
    momentum_threshold_pct: float = 0.10  # 10% price move triggers signal


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

    # Sub-configs (initialized with defaults)
    api: APIConfig = field(default_factory=APIConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)

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
                "max_position_pct": self.risk.max_position_pct,
                "max_daily_loss_pct": self.risk.max_daily_loss_pct,
                "kelly_fraction": self.risk.kelly_fraction,
            },
            "api": {
                "http_timeout": self.api.http_timeout,
                "rate_limit_calls": self.api.polymarket_rate_limit_calls,
                "rate_limit_period": self.api.polymarket_rate_limit_period,
                "circuit_breaker_threshold": self.api.circuit_breaker_threshold,
                "retry_max_attempts": self.api.retry_max_attempts,
            },
            "agent": {
                "loop_interval": self.agent.default_loop_interval,
                "max_consecutive_errors": self.agent.max_consecutive_errors,
                "checkpoint_interval": self.agent.checkpoint_interval,
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


# Global config singleton
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global config singleton, loading if necessary."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reset_config() -> None:
    """Reset the global config singleton (useful for testing)."""
    global _config
    _config = None


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

            # Risk settings (top-level)
            risk = data.get("risk", {})
            config.max_position_size = risk.get("max_position_size", config.max_position_size)
            config.max_daily_loss = risk.get("max_daily_loss", config.max_daily_loss)

            # Risk sub-config
            config.risk.max_position_pct = risk.get(
                "max_position_pct", config.risk.max_position_pct
            )
            config.risk.max_single_trade = risk.get(
                "max_single_trade", config.risk.max_single_trade
            )
            config.risk.max_daily_loss_pct = risk.get(
                "max_daily_loss_pct", config.risk.max_daily_loss_pct
            )
            config.risk.max_total_exposure_pct = risk.get(
                "max_total_exposure_pct", config.risk.max_total_exposure_pct
            )
            config.risk.kelly_fraction = risk.get("kelly_fraction", config.risk.kelly_fraction)
            config.risk.min_confidence_to_trade = risk.get(
                "min_confidence_to_trade", config.risk.min_confidence_to_trade
            )
            config.risk.default_stop_loss_pct = risk.get(
                "default_stop_loss_pct", config.risk.default_stop_loss_pct
            )
            config.risk.default_take_profit_pct = risk.get(
                "default_take_profit_pct", config.risk.default_take_profit_pct
            )

            # API settings
            api = data.get("api", {})
            config.api.http_timeout = api.get("http_timeout", config.api.http_timeout)
            config.api.websocket_timeout = api.get(
                "websocket_timeout", config.api.websocket_timeout
            )
            config.api.polymarket_rate_limit_calls = api.get(
                "rate_limit_calls", config.api.polymarket_rate_limit_calls
            )
            config.api.polymarket_rate_limit_period = api.get(
                "rate_limit_period", config.api.polymarket_rate_limit_period
            )
            config.api.circuit_breaker_threshold = api.get(
                "circuit_breaker_threshold", config.api.circuit_breaker_threshold
            )
            config.api.circuit_breaker_timeout = api.get(
                "circuit_breaker_timeout", config.api.circuit_breaker_timeout
            )
            config.api.retry_max_attempts = api.get(
                "retry_max_attempts", config.api.retry_max_attempts
            )
            config.api.retry_base_delay = api.get("retry_base_delay", config.api.retry_base_delay)
            config.api.retry_max_delay = api.get("retry_max_delay", config.api.retry_max_delay)
            config.api.market_cache_ttl = api.get("market_cache_ttl", config.api.market_cache_ttl)
            config.api.market_cache_max_size = api.get(
                "market_cache_max_size", config.api.market_cache_max_size
            )
            config.api.price_cache_ttl = api.get("price_cache_ttl", config.api.price_cache_ttl)
            config.api.positions_cache_max_size = api.get(
                "positions_cache_max_size", config.api.positions_cache_max_size
            )

            # Agent settings
            agent = data.get("agent", {})
            config.agent.default_loop_interval = agent.get(
                "loop_interval", config.agent.default_loop_interval
            )
            config.agent.max_consecutive_errors = agent.get(
                "max_consecutive_errors", config.agent.max_consecutive_errors
            )
            config.agent.base_backoff = agent.get("base_backoff", config.agent.base_backoff)
            config.agent.max_backoff = agent.get("max_backoff", config.agent.max_backoff)
            config.agent.memory_max_observations = agent.get(
                "memory_max_observations", config.agent.memory_max_observations
            )
            config.agent.memory_max_decisions = agent.get(
                "memory_max_decisions", config.agent.memory_max_decisions
            )
            config.agent.memory_max_trades = agent.get(
                "memory_max_trades", config.agent.memory_max_trades
            )
            config.agent.checkpoint_interval = agent.get(
                "checkpoint_interval", config.agent.checkpoint_interval
            )
            config.agent.risk_save_interval = agent.get(
                "risk_save_interval", config.agent.risk_save_interval
            )

        except Exception:
            pass

    # Load from .env file first (so env vars are available)
    load_dotenv()

    # Try to use secure secrets manager (keyring/encrypted storage)
    try:
        from probablyprofit.utils.secrets import get_secrets_manager

        secrets = get_secrets_manager()

        # Load secrets from secure storage (checks env vars first internally)
        config.openai_api_key = secrets.get("openai_api_key")
        config.anthropic_api_key = secrets.get("anthropic_api_key")
        config.google_api_key = secrets.get("google_api_key")
        config.private_key = secrets.get("private_key")
        config.perplexity_api_key = secrets.get("perplexity_api_key")
        config.twitter_bearer_token = secrets.get("twitter_bearer_token")

        # Migrate plaintext credentials if they exist
        if CREDENTIALS_FILE.exists():
            try:
                with open(CREDENTIALS_FILE) as f:
                    plaintext_creds = yaml.safe_load(f) or {}
                if plaintext_creds:
                    migrated = secrets.migrate_from_plaintext(plaintext_creds)
                    if migrated > 0:
                        logger.info(f"Migrated {migrated} credentials to secure storage")
                        # Backup and remove plaintext file
                        backup_file = CREDENTIALS_FILE.with_suffix(".yaml.bak")
                        CREDENTIALS_FILE.rename(backup_file)
                        logger.info(f"Plaintext credentials backed up to {backup_file}")
            except Exception as e:
                logger.debug(f"Could not migrate plaintext credentials: {e}")

    except ImportError:
        logger.warning("Secrets manager not available, falling back to plaintext credentials")
        # Fallback: Load credentials from plaintext file
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

        # Environment variables override file credentials
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

    # Load Telegram configuration
    config.telegram.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    config.telegram.chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if os.getenv("TELEGRAM_ALERT_LEVELS"):
        config.telegram.alert_levels = [
            level.strip().upper()
            for level in os.getenv("TELEGRAM_ALERT_LEVELS", "").split(",")
            if level.strip()
        ]

    # Load max drawdown from env
    if os.getenv("MAX_DRAWDOWN_PCT"):
        config.risk.max_drawdown_pct = float(os.getenv("MAX_DRAWDOWN_PCT"))

    # Determine if configured
    config.is_configured = len(config.get_available_agents()) > 0

    return config


# Known placeholder/test values that should never be used in production
PLACEHOLDER_PATTERNS = [
    "your_",
    "_here",
    "your-",
    "example",
    "test_",
    "demo_",
    "placeholder",
]

TEST_PRIVATE_KEY = "0x1111111111111111111111111111111111111111111111111111111111111111"


def is_placeholder_value(value: str) -> bool:
    """Check if a value appears to be a placeholder."""
    if not value:
        return True
    value_lower = value.lower()
    return any(pattern in value_lower for pattern in PLACEHOLDER_PATTERNS)


def is_test_private_key(key: Optional[str]) -> bool:
    """Check if private key is the known test key."""
    if not key:
        return False
    # Normalize the key
    normalized = key.lower().strip()
    if not normalized.startswith("0x"):
        normalized = "0x" + normalized
    return normalized == TEST_PRIVATE_KEY.lower()


def validate_production_credentials(config: Config) -> List[str]:
    """
    Validate credentials are safe for production use.

    Returns list of critical issues that must be resolved before live trading.
    """
    issues = []

    # Check private key
    if config.private_key:
        if is_test_private_key(config.private_key):
            issues.append(
                "CRITICAL: Using test private key (0x1111...). "
                "This key has no funds and is publicly known. "
                "Set a real private key for live trading."
            )
        elif is_placeholder_value(config.private_key):
            issues.append(
                "CRITICAL: Private key appears to be a placeholder value. "
                "Set a real private key for live trading."
            )

    # Check AI API keys
    if config.openai_api_key and is_placeholder_value(config.openai_api_key):
        issues.append("OpenAI API key appears to be a placeholder value.")

    if config.anthropic_api_key and is_placeholder_value(config.anthropic_api_key):
        issues.append("Anthropic API key appears to be a placeholder value.")

    if config.google_api_key and is_placeholder_value(config.google_api_key):
        issues.append("Google API key appears to be a placeholder value.")

    return issues


def save_config(config: Config) -> None:
    """Save configuration to user config files."""
    ensure_config_dir()

    # Save non-sensitive config
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(config.to_dict(), f, default_flow_style=False)

    # Save credentials to secure storage
    creds = config.credentials_to_dict()
    if creds:
        try:
            from probablyprofit.utils.secrets import get_secrets_manager

            secrets = get_secrets_manager()
            for key, value in creds.items():
                if value:
                    secrets.set(key, value)
            logger.info("Credentials saved to secure storage")
        except ImportError:
            # Fallback: Save to plaintext file with restricted permissions
            logger.warning("Secrets manager not available, saving credentials to plaintext file")
            with open(CREDENTIALS_FILE, "w") as f:
                yaml.dump(creds, f, default_flow_style=False)
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


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""

    pass


def validate_config(config: Config, strict: bool = False) -> List[str]:
    """
    Validate configuration and return list of warnings/errors.

    Args:
        config: Configuration to validate
        strict: If True, raise exception on critical errors

    Returns:
        List of warning/error messages

    Raises:
        ConfigValidationError: If strict=True and critical errors found
    """
    errors: List[str] = []
    warnings: List[str] = []

    # Check for at least one AI provider
    if not config.get_available_agents():
        errors.append(
            "No AI provider configured. Set at least one of: "
            "OPENAI_API_KEY, ANTHROPIC_API_KEY, or GOOGLE_API_KEY"
        )

    # Check wallet for live trading
    if not config.dry_run and not config.has_wallet():
        errors.append(
            "Live trading enabled but no wallet configured. "
            "Set PRIVATE_KEY or enable dry_run mode"
        )

    # Production credential validation for live trading
    if not config.dry_run:
        prod_issues = validate_production_credentials(config)
        for issue in prod_issues:
            if issue.startswith("CRITICAL:"):
                errors.append(issue)
            else:
                warnings.append(issue)

    # Validate API key formats (basic checks)
    if config.openai_api_key and not config.openai_api_key.startswith("sk-"):
        warnings.append("OpenAI API key doesn't start with 'sk-' - may be invalid")

    if config.anthropic_api_key and not (
        config.anthropic_api_key.startswith("sk-ant-") or config.anthropic_api_key.startswith("sk-")
    ):
        warnings.append("Anthropic API key format looks unusual")

    # Validate private key format
    if config.private_key:
        key = config.private_key
        if key.startswith("0x"):
            key = key[2:]
        if len(key) != 64:
            errors.append(f"Private key should be 64 hex characters (got {len(key)})")
        else:
            try:
                int(key, 16)
            except ValueError:
                errors.append("Private key contains invalid hex characters")

    # Validate risk settings
    if config.risk.max_position_pct <= 0 or config.risk.max_position_pct > 1:
        warnings.append(f"max_position_pct should be 0-1, got {config.risk.max_position_pct}")

    if config.risk.max_daily_loss_pct <= 0 or config.risk.max_daily_loss_pct > 1:
        warnings.append(f"max_daily_loss_pct should be 0-1, got {config.risk.max_daily_loss_pct}")

    if config.risk.kelly_fraction <= 0 or config.risk.kelly_fraction > 1:
        warnings.append(f"kelly_fraction should be 0-1, got {config.risk.kelly_fraction}")

    # Validate API settings
    if config.api.http_timeout <= 0:
        warnings.append(f"http_timeout should be positive, got {config.api.http_timeout}")

    if config.api.polymarket_rate_limit_calls <= 0:
        warnings.append(
            f"rate_limit_calls should be positive, got {config.api.polymarket_rate_limit_calls}"
        )

    # Validate agent settings
    if config.agent.default_loop_interval < 10:
        warnings.append(
            f"loop_interval very low ({config.agent.default_loop_interval}s) - may cause rate limiting"
        )

    if config.initial_capital <= 0:
        warnings.append(f"initial_capital should be positive, got {config.initial_capital}")

    # Log warnings
    for warning in warnings:
        logger.warning(f"Config warning: {warning}")

    # Log errors
    for error in errors:
        logger.error(f"Config error: {error}")

    if strict and errors:
        raise ConfigValidationError(
            f"Configuration validation failed with {len(errors)} error(s):\n"
            + "\n".join(f"  - {e}" for e in errors)
        )

    return errors + warnings


def validate_config_on_startup(strict: bool = True) -> Config:
    """
    Load and validate configuration on application startup.

    Args:
        strict: If True, raise exception on critical errors

    Returns:
        Validated configuration

    Raises:
        ConfigValidationError: If validation fails in strict mode
    """
    config = load_config()
    issues = validate_config(config, strict=strict)

    if issues:
        logger.warning(f"Configuration has {len(issues)} issue(s)")
    else:
        logger.info("Configuration validated successfully")

    return config
