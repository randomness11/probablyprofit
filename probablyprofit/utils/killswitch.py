"""
Emergency Kill Switch

Provides emergency stop functionality for the trading bot:
- File-based kill switch (create file to stop)
- Programmatic activation
- HTTP endpoint for remote kill (via web API)
"""

import os
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, List, Optional

from loguru import logger


# Default kill switch file location
KILL_SWITCH_FILE = Path("/tmp/probablyprofit.stop")
KILL_SWITCH_REASON_FILE = Path("/tmp/probablyprofit.stop.reason")


class KillSwitch:
    """
    Emergency kill switch for halting trading.

    Usage:
        kill_switch = KillSwitch()

        # Check before each trade
        if kill_switch.is_active():
            logger.error("Kill switch active, not trading")
            return

        # Activate programmatically
        kill_switch.activate("Market crash detected")

        # Deactivate
        kill_switch.deactivate()
    """

    def __init__(
        self,
        kill_file: Optional[Path] = None,
        reason_file: Optional[Path] = None,
    ):
        """
        Initialize kill switch.

        Args:
            kill_file: Path to kill switch file
            reason_file: Path to reason file
        """
        self.kill_file = kill_file or KILL_SWITCH_FILE
        self.reason_file = reason_file or KILL_SWITCH_REASON_FILE

        # Callbacks for kill switch activation
        self._on_activate_callbacks: List[Callable[[str], Any]] = []
        self._on_deactivate_callbacks: List[Callable[[], Any]] = []

        # Internal state
        self._programmatic_kill = False
        self._kill_reason: Optional[str] = None

        logger.debug(f"Kill switch initialized. File: {self.kill_file}")

    def is_active(self) -> bool:
        """
        Check if kill switch is active.

        Checks both file-based and programmatic kill switch.
        File-based check takes precedence to allow cross-process coordination.

        Returns:
            True if trading should be halted
        """
        # Check file-based kill switch first (allows cross-process coordination)
        if self.kill_file.exists():
            return True

        # Check programmatic kill (instance-local)
        # Sync with file state - if file was removed externally, clear programmatic flag
        if self._programmatic_kill and not self.kill_file.exists():
            self._programmatic_kill = False
            self._kill_reason = None

        return self._programmatic_kill

    def get_reason(self) -> Optional[str]:
        """
        Get the reason for kill switch activation.

        Returns:
            Reason string or None if not set
        """
        if self._kill_reason:
            return self._kill_reason

        if self.reason_file.exists():
            try:
                return self.reason_file.read_text().strip()
            except Exception:
                pass

        return None

    def activate(self, reason: str = "Manual activation") -> None:
        """
        Activate the kill switch.

        Args:
            reason: Reason for activation
        """
        self._programmatic_kill = True
        self._kill_reason = reason

        # Create kill file for persistence
        try:
            self.kill_file.touch()
            self.reason_file.write_text(f"{reason}\nActivated: {datetime.now().isoformat()}")
            logger.warning(f"Kill switch ACTIVATED: {reason}")
        except Exception as e:
            logger.error(f"Failed to create kill switch file: {e}")

        # Notify callbacks
        for callback in self._on_activate_callbacks:
            try:
                callback(reason)
            except Exception as e:
                logger.error(f"Kill switch callback error: {e}")

    def deactivate(self) -> None:
        """Deactivate the kill switch."""
        self._programmatic_kill = False
        self._kill_reason = None

        # Remove kill files
        try:
            if self.kill_file.exists():
                self.kill_file.unlink()
            if self.reason_file.exists():
                self.reason_file.unlink()
            logger.info("Kill switch DEACTIVATED")
        except Exception as e:
            logger.error(f"Failed to remove kill switch file: {e}")

        # Notify callbacks
        for callback in self._on_deactivate_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Kill switch callback error: {e}")

    def on_activate(self, callback: Callable[[str], Any]) -> None:
        """Register callback for kill switch activation."""
        self._on_activate_callbacks.append(callback)

    def on_deactivate(self, callback: Callable[[], Any]) -> None:
        """Register callback for kill switch deactivation."""
        self._on_deactivate_callbacks.append(callback)

    def check_and_raise(self) -> None:
        """
        Check kill switch and raise exception if active.

        Raises:
            KillSwitchError: If kill switch is active
        """
        if self.is_active():
            reason = self.get_reason() or "Unknown reason"
            raise KillSwitchError(f"Kill switch active: {reason}")


class KillSwitchError(Exception):
    """Raised when kill switch is active."""

    pass


# Singleton instance
_kill_switch: Optional[KillSwitch] = None


def get_kill_switch() -> KillSwitch:
    """Get or create the global kill switch instance."""
    global _kill_switch
    if _kill_switch is None:
        _kill_switch = KillSwitch()
    return _kill_switch


def is_kill_switch_active() -> bool:
    """Check if global kill switch is active."""
    return get_kill_switch().is_active()


def activate_kill_switch(reason: str = "Manual activation") -> None:
    """Activate the global kill switch."""
    get_kill_switch().activate(reason)


def deactivate_kill_switch() -> None:
    """Deactivate the global kill switch."""
    get_kill_switch().deactivate()


def setup_signal_handlers() -> None:
    """
    Setup signal handlers for graceful shutdown.

    Handles:
    - SIGTERM: Graceful shutdown
    - SIGINT: Keyboard interrupt (Ctrl+C)
    - SIGUSR1: Activate kill switch
    - SIGUSR2: Deactivate kill switch
    """

    def handle_sigterm(signum, frame):
        logger.info("Received SIGTERM, activating kill switch for graceful shutdown")
        activate_kill_switch("SIGTERM received")
        sys.exit(0)

    def handle_sigint(signum, frame):
        logger.info("Received SIGINT (Ctrl+C), activating kill switch")
        activate_kill_switch("SIGINT received (Ctrl+C)")
        sys.exit(0)

    def handle_sigusr1(signum, frame):
        logger.warning("Received SIGUSR1, activating kill switch")
        activate_kill_switch("SIGUSR1 signal received")

    def handle_sigusr2(signum, frame):
        logger.info("Received SIGUSR2, deactivating kill switch")
        deactivate_kill_switch()

    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigint)

    # SIGUSR1/2 may not be available on Windows
    if hasattr(signal, "SIGUSR1"):
        signal.signal(signal.SIGUSR1, handle_sigusr1)
    if hasattr(signal, "SIGUSR2"):
        signal.signal(signal.SIGUSR2, handle_sigusr2)

    logger.info("Signal handlers configured for graceful shutdown")
