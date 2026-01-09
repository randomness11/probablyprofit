"""
Example: Discord Notification Plugin

Shows how to create a plugin that sends trade notifications to Discord.
"""
from typing import Dict, Any
import os
from loguru import logger

from probablyprofit.plugins import registry, PluginType
from probablyprofit.plugins.base import OutputPlugin, PluginConfig


@registry.register(
    "discord_notifications",
    PluginType.OUTPUT,
    version="1.0.0",
    author="community",
    description="Send trade notifications to Discord webhook"
)
class DiscordNotificationPlugin(OutputPlugin):
    """
    Sends trading events to a Discord webhook.
    
    Usage:
        Set DISCORD_WEBHOOK_URL in your .env file, then:
        
        from probablyprofit.plugins.community.discord_plugin import DiscordNotificationPlugin
        
        plugin = DiscordNotificationPlugin()
        await plugin.send("trade", {"market": "...", "action": "buy"})
    """
    
    def __init__(self, config: PluginConfig = None, webhook_url: str = None):
        super().__init__(config)
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL", "")
    
    async def send(self, event_type: str, data: Dict[str, Any]) -> None:
        """Send notification to Discord."""
        if not self.webhook_url:
            logger.debug("Discord webhook URL not configured, skipping")
            return
        
        # Format message based on event type
        if event_type == "trade":
            emoji = "📈" if data.get("action") == "buy" else "📉"
            title = f"{emoji} Trade Executed"
            description = (
                f"**Market:** {data.get('market', 'Unknown')}\n"
                f"**Action:** {data.get('action', 'Unknown').upper()}\n"
                f"**Size:** ${data.get('size', 0):.2f}\n"
                f"**Price:** {data.get('price', 0):.2f}"
            )
        elif event_type == "error":
            title = "❌ Error"
            description = f"```{data.get('message', str(data))}```"
        elif event_type == "alert":
            title = "⚠️ Alert"
            description = data.get("message", str(data))
        else:
            title = f"📢 {event_type.title()}"
            description = str(data)
        
        payload = {
            "embeds": [{
                "title": title,
                "description": description,
                "color": self._get_color(event_type)
            }]
        }
        
        # In production, you'd POST to the webhook
        # import httpx
        # async with httpx.AsyncClient() as client:
        #     await client.post(self.webhook_url, json=payload)
        
        logger.info(f"[Discord] Would send: {title}")
    
    def _get_color(self, event_type: str) -> int:
        """Get Discord embed color based on event type."""
        colors = {
            "trade": 0x00FF00,   # Green
            "error": 0xFF0000,   # Red
            "alert": 0xFFFF00,   # Yellow
        }
        return colors.get(event_type, 0x0099FF)  # Default blue
