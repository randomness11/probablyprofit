"""
Example Plugins

Sample plugins demonstrating the plugin architecture.
"""

from typing import Any, Dict, List

from loguru import logger

from probablyprofit.plugins import PluginType, registry
from probablyprofit.plugins.base import DataSourcePlugin, OutputPlugin, PluginConfig, StrategyPlugin
from probablyprofit.plugins.hooks import Hook, hooks

# ============================================================================
# Example: Slack Notification Plugin
# ============================================================================


@registry.register(
    "slack_notifications",
    PluginType.OUTPUT,
    version="1.0.0",
    author="probablyprofit",
    description="Send trade notifications to Slack",
)
class SlackNotificationPlugin(OutputPlugin):
    """Sends trading events to a Slack webhook."""

    def __init__(self, config: PluginConfig = None, webhook_url: str = None):
        super().__init__(config)
        self.webhook_url = webhook_url or config.options.get("webhook_url", "") if config else ""

    async def send(self, event_type: str, data: Dict[str, Any]) -> None:
        """Send notification to Slack."""
        if not self.webhook_url:
            logger.warning("Slack webhook URL not configured")
            return

        # Format message
        emoji = {"trade": "📈", "error": "❌", "alert": "⚠️"}.get(event_type, "📢")
        message = f"{emoji} *{event_type.upper()}*\n```{data}```"

        # In real implementation, would POST to webhook
        logger.info(f"[Slack] Would send: {message[:100]}...")


# ============================================================================
# Example: Whale Tracker Data Source
# ============================================================================


@registry.register(
    "whale_tracker",
    PluginType.DATA_SOURCE,
    version="1.0.0",
    description="Track large wallet movements on Polymarket",
)
class WhaleTrackerPlugin(DataSourcePlugin):
    """Tracks large bets on Polymarket."""

    def __init__(self, config: PluginConfig = None, min_bet_size: float = 1000.0):
        super().__init__(config)
        self.min_bet_size = min_bet_size

    async def fetch(self, query: str) -> Dict[str, Any]:
        """Fetch whale activity for a market."""
        # Mock implementation
        return {
            "market_id": query,
            "large_bets": [
                {"side": "YES", "size": 5000, "timestamp": "2024-01-07T12:00:00Z"},
                {"side": "NO", "size": 3000, "timestamp": "2024-01-07T11:30:00Z"},
            ],
            "net_flow": 2000,  # Positive = bullish whale activity
        }


# ============================================================================
# Example: Momentum Strategy Plugin
# ============================================================================


@registry.register(
    "momentum", PluginType.STRATEGY, version="1.0.0", description="Trade based on price momentum"
)
class MomentumStrategyPlugin(StrategyPlugin):
    """Simple momentum-based strategy."""

    def __init__(self, config: PluginConfig = None, lookback_hours: int = 24):
        super().__init__(config)
        self.lookback_hours = lookback_hours

    def get_prompt(self) -> str:
        return f"""
You are a momentum trader. Your strategy:
1. BUY when price has been rising over the last {self.lookback_hours} hours
2. SELL when price has been falling
3. HOLD when trend is unclear

Focus on markets with high volume and clear directional movement.
"""

    def filter_markets(self, markets: List[Any]) -> List[Any]:
        """Filter to markets with sufficient volume."""
        return [m for m in markets if getattr(m, "volume", 0) > 1000]

    def score_market(self, market: Any) -> float:
        """Score based on momentum (mock)."""
        # In real implementation, would calculate actual momentum
        return 0.7


# ============================================================================
# Example Hook Handlers
# ============================================================================


@hooks.on(Hook.AFTER_TRADE, priority=100, name="trade_logger")
async def log_trades(data):
    """Log all executed trades."""
    logger.info(f"🔔 Trade executed: {data}")


@hooks.on(Hook.ON_RISK_BREACH, priority=100, name="risk_alert")
async def alert_risk_breach(data):
    """Alert on risk limit breaches."""
    logger.warning(f"⚠️ RISK BREACH: {data}")


# ============================================================================
# Helper to list available plugins
# ============================================================================


def list_example_plugins() -> Dict[str, List[str]]:
    """List all example plugins that get registered."""
    return registry.list_plugins()
