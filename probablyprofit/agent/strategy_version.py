"""
Strategy Versioning

Provides versioning and tracking for trading strategies to ensure
reproducibility and auditability of trading decisions.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

from loguru import logger


@dataclass
class StrategyVersion:
    """
    Represents a versioned trading strategy.

    Attributes:
        content: The strategy text/content
        version_hash: SHA-256 hash of the content
        created_at: When this version was created
        name: Optional human-readable name
        description: Optional description
        metadata: Additional metadata
    """

    content: str
    version_hash: str
    created_at: datetime = field(default_factory=datetime.now)
    name: Optional[str] = None
    description: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_content(
        cls,
        content: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "StrategyVersion":
        """
        Create a StrategyVersion from content.

        Args:
            content: Strategy text
            name: Optional name
            description: Optional description
            metadata: Optional metadata

        Returns:
            StrategyVersion instance
        """
        version_hash = cls.compute_hash(content)
        return cls(
            content=content,
            version_hash=version_hash,
            name=name,
            description=description,
            metadata=metadata or {},
        )

    @staticmethod
    def compute_hash(content: str) -> str:
        """
        Compute SHA-256 hash of content.

        Args:
            content: String to hash

        Returns:
            Hex-encoded hash (first 12 characters for readability)
        """
        full_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return full_hash[:12]  # Short version for display

    @property
    def short_hash(self) -> str:
        """Get first 8 characters of hash."""
        return self.version_hash[:8]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "version_hash": self.version_hash,
            "created_at": self.created_at.isoformat(),
            "name": self.name,
            "description": self.description,
            "metadata": self.metadata,
            "content_length": len(self.content),
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    def __str__(self) -> str:
        name_part = f" ({self.name})" if self.name else ""
        return f"Strategy v{self.short_hash}{name_part}"


class StrategyRegistry:
    """
    Registry for tracking strategy versions.

    Maintains a history of all strategy versions used, enabling:
    - Auditing which strategy was active when a trade was made
    - Rolling back to previous strategies
    - Comparing strategy performance across versions
    """

    def __init__(self):
        self._versions: Dict[str, StrategyVersion] = {}
        self._history: list = []  # List of (timestamp, version_hash) tuples
        self._active_version: Optional[str] = None

    def register(
        self,
        content: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        activate: bool = True,
    ) -> StrategyVersion:
        """
        Register a new strategy version.

        Args:
            content: Strategy text
            name: Optional name
            description: Optional description
            metadata: Optional metadata
            activate: Set as active version

        Returns:
            StrategyVersion instance
        """
        version = StrategyVersion.from_content(
            content=content,
            name=name,
            description=description,
            metadata=metadata,
        )

        # Store if not already registered
        if version.version_hash not in self._versions:
            self._versions[version.version_hash] = version
            logger.info(f"Registered new strategy version: {version}")
        else:
            logger.debug(f"Strategy version already registered: {version.short_hash}")

        # Activate if requested
        if activate:
            self.activate(version.version_hash)

        return version

    def activate(self, version_hash: str) -> bool:
        """
        Set a version as the active strategy.

        Args:
            version_hash: Hash of version to activate

        Returns:
            True if activated successfully
        """
        if version_hash not in self._versions:
            logger.error(f"Cannot activate unknown version: {version_hash}")
            return False

        self._active_version = version_hash
        self._history.append((datetime.now(), version_hash))
        logger.info(f"Activated strategy version: {version_hash[:8]}")
        return True

    def get_active(self) -> Optional[StrategyVersion]:
        """Get the currently active strategy version."""
        if self._active_version:
            return self._versions.get(self._active_version)
        return None

    def get_version(self, version_hash: str) -> Optional[StrategyVersion]:
        """Get a specific version by hash."""
        return self._versions.get(version_hash)

    def get_all_versions(self) -> Dict[str, StrategyVersion]:
        """Get all registered versions."""
        return self._versions.copy()

    def get_history(self) -> list:
        """Get activation history."""
        return self._history.copy()

    def get_version_at_time(self, timestamp: datetime) -> Optional[StrategyVersion]:
        """
        Get the strategy version that was active at a given time.

        Args:
            timestamp: Time to query

        Returns:
            Strategy version active at that time, or None
        """
        active_hash = None
        for ts, version_hash in self._history:
            if ts <= timestamp:
                active_hash = version_hash
            else:
                break

        if active_hash:
            return self._versions.get(active_hash)
        return None

    @property
    def active_version_hash(self) -> Optional[str]:
        """Get the hash of the active version."""
        return self._active_version

    @property
    def version_count(self) -> int:
        """Get total number of registered versions."""
        return len(self._versions)

    def to_dict(self) -> Dict[str, Any]:
        """Convert registry state to dictionary."""
        return {
            "active_version": self._active_version,
            "version_count": len(self._versions),
            "versions": {h: v.to_dict() for h, v in self._versions.items()},
            "history_length": len(self._history),
        }


# Global registry singleton
_strategy_registry: Optional[StrategyRegistry] = None


def get_strategy_registry() -> StrategyRegistry:
    """Get the global strategy registry."""
    global _strategy_registry
    if _strategy_registry is None:
        _strategy_registry = StrategyRegistry()
    return _strategy_registry


def register_strategy(
    content: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> StrategyVersion:
    """
    Convenience function to register a strategy.

    Args:
        content: Strategy text
        name: Optional name
        description: Optional description

    Returns:
        StrategyVersion instance
    """
    return get_strategy_registry().register(
        content=content,
        name=name,
        description=description,
    )


def get_active_strategy() -> Optional[StrategyVersion]:
    """Get the currently active strategy."""
    return get_strategy_registry().get_active()
