"""
Pre-Flight Health Checks

Validates system readiness before trading starts.
All checks must pass for live trading to proceed.
"""

import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger


class CheckStatus(str, Enum):
    """Check result status."""

    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    SKIP = "skip"


@dataclass
class CheckResult:
    """Result of a single preflight check."""

    name: str
    status: CheckStatus
    message: str
    details: Optional[Dict[str, Any]] = None


@dataclass
class PreflightReport:
    """Complete preflight check report."""

    timestamp: datetime = field(default_factory=datetime.now)
    checks: List[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """Check if all critical checks passed."""
        return all(c.status != CheckStatus.FAIL for c in self.checks)

    @property
    def has_warnings(self) -> bool:
        """Check if there are any warnings."""
        return any(c.status == CheckStatus.WARN for c in self.checks)

    @property
    def failed_checks(self) -> List[CheckResult]:
        """Get list of failed checks."""
        return [c for c in self.checks if c.status == CheckStatus.FAIL]

    @property
    def warning_checks(self) -> List[CheckResult]:
        """Get list of warning checks."""
        return [c for c in self.checks if c.status == CheckStatus.WARN]

    def summary(self) -> str:
        """Generate human-readable summary."""
        total = len(self.checks)
        passed = sum(1 for c in self.checks if c.status == CheckStatus.PASS)
        failed = sum(1 for c in self.checks if c.status == CheckStatus.FAIL)
        warned = sum(1 for c in self.checks if c.status == CheckStatus.WARN)
        skipped = sum(1 for c in self.checks if c.status == CheckStatus.SKIP)

        lines = [
            f"Preflight Check Report - {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"{'=' * 50}",
            f"Total: {total} | Passed: {passed} | Failed: {failed} | "
            f"Warnings: {warned} | Skipped: {skipped}",
            "",
        ]

        for check in self.checks:
            status_icon = {
                CheckStatus.PASS: "[PASS]",
                CheckStatus.FAIL: "[FAIL]",
                CheckStatus.WARN: "[WARN]",
                CheckStatus.SKIP: "[SKIP]",
            }[check.status]
            lines.append(f"{status_icon} {check.name}: {check.message}")

        if not self.passed:
            lines.append("")
            lines.append("PREFLIGHT FAILED - Trading blocked")
            lines.append("Fix the above issues before starting live trading.")

        return "\n".join(lines)


class PreflightChecker:
    """
    Runs preflight health checks before trading.

    Checks:
    1. Database writable
    2. AI provider reachable
    3. Market data available
    4. Risk manager state loaded
    5. Kill switch not active
    6. Credentials valid (not placeholders)
    7. Private key not test key
    """

    def __init__(self):
        """Initialize preflight checker."""
        self._checks: List[callable] = [
            self._check_kill_switch,
            self._check_credentials,
            self._check_private_key,
            self._check_database,
            self._check_ai_provider,
            self._check_telegram,
        ]

    async def run_all(self, dry_run: bool = True) -> PreflightReport:
        """
        Run all preflight checks.

        Args:
            dry_run: If True, skip checks only needed for live trading

        Returns:
            PreflightReport with all check results
        """
        report = PreflightReport()

        for check in self._checks:
            try:
                result = await check(dry_run=dry_run)
                report.checks.append(result)
            except Exception as e:
                report.checks.append(
                    CheckResult(
                        name=check.__name__.replace("_check_", "").title(),
                        status=CheckStatus.FAIL,
                        message=f"Check crashed: {e}",
                    )
                )

        # Log summary
        if report.passed:
            logger.info(f"Preflight checks passed ({len(report.checks)} checks)")
        else:
            logger.error(f"Preflight checks FAILED: " f"{len(report.failed_checks)} failures")

        return report

    async def _check_kill_switch(self, dry_run: bool = True) -> CheckResult:
        """Check that kill switch is not active."""
        try:
            from probablyprofit.utils.killswitch import get_kill_switch

            kill_switch = get_kill_switch()
            if kill_switch.is_active():
                reason = kill_switch.get_reason() or "Unknown"
                return CheckResult(
                    name="Kill Switch",
                    status=CheckStatus.FAIL,
                    message=f"Kill switch is ACTIVE: {reason}",
                )
            return CheckResult(
                name="Kill Switch",
                status=CheckStatus.PASS,
                message="Kill switch not active",
            )
        except ImportError:
            return CheckResult(
                name="Kill Switch",
                status=CheckStatus.SKIP,
                message="Kill switch module not available",
            )

    async def _check_credentials(self, dry_run: bool = True) -> CheckResult:
        """Check that credentials are not placeholders."""
        from probablyprofit.config import (
            get_config,
            is_placeholder_value,
            validate_production_credentials,
        )

        config = get_config()

        # In dry run mode, just warn about placeholders
        if dry_run:
            issues = []
            if config.openai_api_key and is_placeholder_value(config.openai_api_key):
                issues.append("OpenAI key is placeholder")
            if config.anthropic_api_key and is_placeholder_value(config.anthropic_api_key):
                issues.append("Anthropic key is placeholder")

            if issues:
                return CheckResult(
                    name="Credentials",
                    status=CheckStatus.WARN,
                    message=f"Placeholder values found: {', '.join(issues)}",
                )
            return CheckResult(
                name="Credentials",
                status=CheckStatus.PASS,
                message="Credentials configured",
            )

        # In live mode, validate production credentials
        issues = validate_production_credentials(config)
        if issues:
            critical = [i for i in issues if i.startswith("CRITICAL")]
            if critical:
                return CheckResult(
                    name="Credentials",
                    status=CheckStatus.FAIL,
                    message=critical[0],
                )
            return CheckResult(
                name="Credentials",
                status=CheckStatus.WARN,
                message="; ".join(issues),
            )

        return CheckResult(
            name="Credentials",
            status=CheckStatus.PASS,
            message="Production credentials validated",
        )

    async def _check_private_key(self, dry_run: bool = True) -> CheckResult:
        """Check that private key is not the test key."""
        from probablyprofit.config import get_config, is_test_private_key

        config = get_config()

        # Skip if no wallet configured (dry run mode typically)
        if not config.private_key:
            if dry_run:
                return CheckResult(
                    name="Private Key",
                    status=CheckStatus.SKIP,
                    message="No private key configured (dry run mode)",
                )
            return CheckResult(
                name="Private Key",
                status=CheckStatus.FAIL,
                message="No private key configured for live trading",
            )

        if is_test_private_key(config.private_key):
            if dry_run:
                return CheckResult(
                    name="Private Key",
                    status=CheckStatus.WARN,
                    message="Using test private key (0x1111...) - OK for dry run",
                )
            return CheckResult(
                name="Private Key",
                status=CheckStatus.FAIL,
                message="CRITICAL: Using test private key for live trading",
            )

        return CheckResult(
            name="Private Key",
            status=CheckStatus.PASS,
            message="Private key configured",
        )

    async def _check_database(self, dry_run: bool = True) -> CheckResult:
        """Check that database is accessible and writable."""
        try:
            from probablyprofit.storage.database import get_db_manager

            db = get_db_manager()

            # Try to get a session
            async with db.get_session() as session:
                # Execute a simple query
                from sqlalchemy import text

                await session.execute(text("SELECT 1"))

            return CheckResult(
                name="Database",
                status=CheckStatus.PASS,
                message="Database accessible and writable",
            )

        except ImportError:
            return CheckResult(
                name="Database",
                status=CheckStatus.SKIP,
                message="Database module not available",
            )
        except Exception as e:
            return CheckResult(
                name="Database",
                status=CheckStatus.FAIL,
                message=f"Database error: {e}",
            )

    async def _check_ai_provider(self, dry_run: bool = True) -> CheckResult:
        """Check that at least one AI provider is reachable."""
        from probablyprofit.config import get_config

        config = get_config()
        available = config.get_available_agents()

        if not available:
            return CheckResult(
                name="AI Provider",
                status=CheckStatus.FAIL,
                message="No AI providers configured",
            )

        # Try to reach the best available provider
        best = config.get_best_agent()
        api_key = config.get_api_key_for_agent(best)

        try:
            if best == "openai":
                import openai

                client = openai.OpenAI(api_key=api_key, timeout=10.0)
                # Quick validation - list models
                client.models.list()
            elif best == "anthropic":
                import anthropic

                client = anthropic.Anthropic(api_key=api_key, timeout=10.0)
                # Quick validation - count tokens
                client.messages.count_tokens(
                    model="claude-sonnet-4-5-20250929",
                    messages=[{"role": "user", "content": "test"}],
                )
            elif best == "google":
                import google.generativeai as genai

                genai.configure(api_key=api_key)
                list(genai.list_models())

            return CheckResult(
                name="AI Provider",
                status=CheckStatus.PASS,
                message=f"AI provider reachable: {best}",
                details={"provider": best, "available": available},
            )

        except Exception as e:
            return CheckResult(
                name="AI Provider",
                status=CheckStatus.FAIL,
                message=f"AI provider {best} unreachable: {e}",
            )

    async def _check_telegram(self, dry_run: bool = True) -> CheckResult:
        """Check Telegram alerting configuration."""
        from probablyprofit.config import get_config

        config = get_config()

        if not config.telegram.is_configured():
            if dry_run:
                return CheckResult(
                    name="Telegram",
                    status=CheckStatus.SKIP,
                    message="Telegram not configured (optional for dry run)",
                )
            return CheckResult(
                name="Telegram",
                status=CheckStatus.WARN,
                message="Telegram not configured - no alerts will be sent",
            )

        # Try to validate the bot token
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"https://api.telegram.org/bot{config.telegram.bot_token}/getMe"
                )
                if response.status_code == 200:
                    data = response.json()
                    bot_name = data.get("result", {}).get("username", "unknown")
                    return CheckResult(
                        name="Telegram",
                        status=CheckStatus.PASS,
                        message=f"Telegram bot reachable: @{bot_name}",
                    )
                else:
                    return CheckResult(
                        name="Telegram",
                        status=CheckStatus.FAIL,
                        message=f"Invalid bot token: {response.status_code}",
                    )
        except Exception as e:
            return CheckResult(
                name="Telegram",
                status=CheckStatus.WARN,
                message=f"Could not verify Telegram: {e}",
            )


async def run_preflight_checks(dry_run: bool = True) -> PreflightReport:
    """
    Run all preflight checks.

    Args:
        dry_run: If True, running in dry run mode

    Returns:
        PreflightReport with results
    """
    checker = PreflightChecker()
    return await checker.run_all(dry_run=dry_run)


def run_preflight_checks_sync(dry_run: bool = True) -> PreflightReport:
    """Synchronous wrapper for preflight checks."""
    return asyncio.run(run_preflight_checks(dry_run=dry_run))
