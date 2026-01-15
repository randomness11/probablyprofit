"""
Telegram Alerting System

Sends real-time alerts via Telegram bot for:
- Trade executions
- Risk limit warnings
- System status updates
- Error notifications
"""

import asyncio
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Deque, Dict, List, Optional

import httpx
from loguru import logger

from probablyprofit.config import get_config


class AlertLevel(str, Enum):
    """Alert severity levels."""

    INFO = "INFO"  # Trade executed, bot started/stopped
    WARNING = "WARNING"  # Risk limit approaching, reconciliation issues
    CRITICAL = "CRITICAL"  # Max drawdown, circuit breaker, errors


@dataclass
class Alert:
    """Represents a single alert."""

    level: AlertLevel
    title: str
    message: str
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = None


class TelegramAlerter:
    """
    Telegram alert sender with rate limiting.

    Features:
    - Configurable alert levels
    - Rate limiting (max 30 messages/minute by default)
    - Message formatting with emojis
    - Async/await support
    - Batching of rapid alerts
    """

    # Level to emoji mapping
    LEVEL_EMOJI = {
        AlertLevel.INFO: "\u2139\ufe0f",  # ℹ️
        AlertLevel.WARNING: "\u26a0\ufe0f",  # ⚠️
        AlertLevel.CRITICAL: "\U0001f6a8",  # 🚨
    }

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        alert_levels: Optional[List[str]] = None,
        rate_limit_per_minute: int = 30,
    ):
        """
        Initialize Telegram alerter.

        Args:
            bot_token: Telegram bot token (from @BotFather)
            chat_id: Chat ID to send messages to
            alert_levels: List of levels to send (e.g., ["WARNING", "CRITICAL"])
            rate_limit_per_minute: Max messages per minute
        """
        config = get_config()

        self.bot_token = bot_token or config.telegram.bot_token
        self.chat_id = chat_id or config.telegram.chat_id
        self.alert_levels = set(
            AlertLevel(level) for level in (alert_levels or config.telegram.alert_levels)
        )
        self.rate_limit = rate_limit_per_minute

        # Rate limiting state
        self._message_times: Deque[float] = deque(maxlen=rate_limit_per_minute)
        self._lock = asyncio.Lock()

        # HTTP client
        self._client: Optional[httpx.AsyncClient] = None

        # Alert history (for debugging)
        self._alert_history: Deque[Alert] = deque(maxlen=100)

        # Suppress repeated alerts
        self._last_alert_hash: Optional[str] = None
        self._repeat_count = 0

        logger.info(
            f"Telegram alerter initialized. "
            f"Levels: {[l.value for l in self.alert_levels]}, "
            f"Rate limit: {rate_limit_per_minute}/min"
        )

    @property
    def is_configured(self) -> bool:
        """Check if alerter is properly configured."""
        return bool(self.bot_token and self.chat_id)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _can_send(self) -> bool:
        """Check if we can send a message (rate limiting)."""
        now = time.time()

        # Remove old timestamps (older than 60 seconds)
        while self._message_times and now - self._message_times[0] > 60:
            self._message_times.popleft()

        return len(self._message_times) < self.rate_limit

    def _record_send(self) -> None:
        """Record that a message was sent."""
        self._message_times.append(time.time())

    def _format_message(self, alert: Alert) -> str:
        """Format alert for Telegram (with markdown)."""
        emoji = self.LEVEL_EMOJI.get(alert.level, "")
        timestamp = alert.timestamp.strftime("%H:%M:%S")

        lines = [
            f"{emoji} *{alert.level.value}*: {alert.title}",
            f"_{timestamp}_",
            "",
            alert.message,
        ]

        # Add metadata if present
        if alert.metadata:
            lines.append("")
            for key, value in alert.metadata.items():
                if isinstance(value, float):
                    lines.append(f"• {key}: `{value:.4f}`")
                else:
                    lines.append(f"• {key}: `{value}`")

        return "\n".join(lines)

    async def send_alert(
        self,
        level: AlertLevel,
        title: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
        force: bool = False,
    ) -> bool:
        """
        Send an alert via Telegram.

        Args:
            level: Alert severity level
            title: Short alert title
            message: Alert message body
            metadata: Optional key-value data to include
            force: Send even if rate limited or level filtered

        Returns:
            True if alert was sent successfully
        """
        # Check if configured
        if not self.is_configured:
            logger.debug(f"Telegram not configured, skipping alert: {title}")
            return False

        # Check level filter (unless forced)
        if not force and level not in self.alert_levels:
            logger.debug(f"Alert level {level} not in configured levels, skipping")
            return False

        # Create alert object
        alert = Alert(
            level=level,
            title=title,
            message=message,
            timestamp=datetime.now(),
            metadata=metadata,
        )

        # Suppress repeated identical alerts
        alert_hash = f"{level}:{title}:{message}"
        if alert_hash == self._last_alert_hash and not force:
            self._repeat_count += 1
            if self._repeat_count <= 3:
                logger.debug(f"Suppressing repeated alert: {title}")
                return False
            # After 3 repeats, send a summary
            message = f"{message}\n\n(Repeated {self._repeat_count} times)"
            self._repeat_count = 0

        self._last_alert_hash = alert_hash

        async with self._lock:
            # Check rate limit
            if not force and not self._can_send():
                logger.warning(f"Rate limited, dropping alert: {title}")
                return False

            try:
                client = await self._get_client()
                formatted_message = self._format_message(alert)

                response = await client.post(
                    f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                    json={
                        "chat_id": self.chat_id,
                        "text": formatted_message,
                        "parse_mode": "Markdown",
                        "disable_web_page_preview": True,
                    },
                )

                if response.status_code == 200:
                    self._record_send()
                    self._alert_history.append(alert)
                    logger.debug(f"Telegram alert sent: {title}")
                    return True
                else:
                    logger.error(f"Telegram API error: {response.status_code} - {response.text}")
                    return False

            except Exception as e:
                logger.error(f"Failed to send Telegram alert: {e}")
                return False

    # Convenience methods for common alerts

    async def info(self, title: str, message: str, **metadata) -> bool:
        """Send INFO level alert."""
        return await self.send_alert(AlertLevel.INFO, title, message, metadata or None)

    async def warning(self, title: str, message: str, **metadata) -> bool:
        """Send WARNING level alert."""
        return await self.send_alert(AlertLevel.WARNING, title, message, metadata or None)

    async def critical(self, title: str, message: str, **metadata) -> bool:
        """Send CRITICAL level alert."""
        return await self.send_alert(AlertLevel.CRITICAL, title, message, metadata or None)

    # Pre-defined alert types

    async def alert_trade_executed(
        self,
        market: str,
        side: str,
        size: float,
        price: float,
        pnl: Optional[float] = None,
    ) -> bool:
        """Alert for trade execution."""
        message = f"{side} {size:.2f} shares @ ${price:.4f}"
        metadata = {"market": market, "side": side, "size": size, "price": price}
        if pnl is not None:
            metadata["pnl"] = pnl
            if pnl >= 0:
                message += f"\nP&L: +${pnl:.2f}"
            else:
                message += f"\nP&L: -${abs(pnl):.2f}"

        return await self.info("Trade Executed", message, **metadata)

    async def alert_daily_loss_approaching(
        self,
        current_loss: float,
        max_loss: float,
        pct: float,
    ) -> bool:
        """Alert when approaching daily loss limit."""
        return await self.warning(
            "Daily Loss Limit Approaching",
            f"Current loss: ${abs(current_loss):.2f}\n" f"Limit: ${max_loss:.2f} ({pct:.0%} used)",
            current_loss=current_loss,
            max_loss=max_loss,
            usage_pct=pct,
        )

    async def alert_daily_loss_exceeded(
        self,
        current_loss: float,
        max_loss: float,
    ) -> bool:
        """Alert when daily loss limit exceeded."""
        return await self.critical(
            "Daily Loss Limit Exceeded",
            f"TRADING HALTED\n\n"
            f"Daily loss: ${abs(current_loss):.2f}\n"
            f"Limit was: ${max_loss:.2f}",
            current_loss=current_loss,
            max_loss=max_loss,
        )

    async def alert_max_drawdown_exceeded(
        self,
        drawdown_pct: float,
        peak_capital: float,
        current_capital: float,
    ) -> bool:
        """Alert when max drawdown exceeded."""
        return await self.critical(
            "Max Drawdown Exceeded",
            f"TRADING HALTED\n\n"
            f"Drawdown: {drawdown_pct:.1%}\n"
            f"Peak: ${peak_capital:.2f}\n"
            f"Current: ${current_capital:.2f}",
            drawdown_pct=drawdown_pct,
            peak_capital=peak_capital,
            current_capital=current_capital,
        )

    async def alert_circuit_breaker_tripped(
        self,
        api_name: str,
        failure_count: int,
    ) -> bool:
        """Alert when circuit breaker trips."""
        return await self.critical(
            "Circuit Breaker Tripped",
            f"API: {api_name}\n"
            f"Failures: {failure_count}\n\n"
            "Trading paused until circuit resets.",
            api=api_name,
            failures=failure_count,
        )

    async def alert_bot_started(self, agent_name: str, capital: float) -> bool:
        """Alert when bot starts."""
        return await self.info(
            "Bot Started",
            f"Agent: {agent_name}\n" f"Capital: ${capital:.2f}",
            agent=agent_name,
            capital=capital,
        )

    async def alert_bot_stopped(
        self,
        agent_name: str,
        reason: str,
        final_capital: float,
    ) -> bool:
        """Alert when bot stops."""
        return await self.info(
            "Bot Stopped",
            f"Agent: {agent_name}\n" f"Reason: {reason}\n" f"Final Capital: ${final_capital:.2f}",
            agent=agent_name,
            reason=reason,
            final_capital=final_capital,
        )

    async def alert_reconciliation_issue(
        self,
        order_id: str,
        local_status: str,
        exchange_status: str,
    ) -> bool:
        """Alert when order reconciliation finds discrepancy."""
        return await self.warning(
            "Order Reconciliation Discrepancy",
            f"Order: {order_id}\n"
            f"Local status: {local_status}\n"
            f"Exchange status: {exchange_status}",
            order_id=order_id,
            local_status=local_status,
            exchange_status=exchange_status,
        )

    async def alert_error(self, error_type: str, error_message: str) -> bool:
        """Alert for general errors."""
        return await self.critical(
            f"Error: {error_type}",
            error_message,
            error_type=error_type,
        )


# Singleton alerter instance
_alerter: Optional[TelegramAlerter] = None


def get_alerter() -> TelegramAlerter:
    """Get or create the global Telegram alerter instance."""
    global _alerter
    if _alerter is None:
        _alerter = TelegramAlerter()
    return _alerter


async def send_alert(
    level: AlertLevel,
    title: str,
    message: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """Convenience function to send an alert using the global alerter."""
    return await get_alerter().send_alert(level, title, message, metadata)
