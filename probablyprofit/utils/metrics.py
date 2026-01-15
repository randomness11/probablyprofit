"""
Metrics and Observability for ProbablyProfit

Provides metrics collection, aggregation, and export capabilities
for monitoring trading bot performance and health.

Supports:
- Counter metrics (requests, trades, errors)
- Gauge metrics (balance, positions, exposure)
- Histogram metrics (latencies, sizes)
- Prometheus-compatible export
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from threading import Lock
from typing import Any, Callable, Dict, List, Optional

from loguru import logger


@dataclass
class MetricPoint:
    """A single metric data point."""

    timestamp: datetime
    value: float
    labels: Dict[str, str] = field(default_factory=dict)


class Counter:
    """
    Monotonically increasing counter metric.

    Usage:
        requests = Counter("http_requests_total", "Total HTTP requests")
        requests.inc()
        requests.inc(labels={"endpoint": "/api/status"})
    """

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self._values: Dict[str, float] = defaultdict(float)
        self._lock = Lock()

    def inc(self, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        """Increment counter."""
        label_key = self._labels_to_key(labels)
        with self._lock:
            self._values[label_key] += value

    def get(self, labels: Optional[Dict[str, str]] = None) -> float:
        """Get current counter value."""
        label_key = self._labels_to_key(labels)
        with self._lock:
            return self._values[label_key]

    def reset(self) -> None:
        """Reset all values (use with caution)."""
        with self._lock:
            self._values.clear()

    def _labels_to_key(self, labels: Optional[Dict[str, str]]) -> str:
        if not labels:
            return ""
        return ",".join(f"{k}={v}" for k, v in sorted(labels.items()))

    def to_prometheus(self) -> str:
        """Export in Prometheus format."""
        lines = [f"# HELP {self.name} {self.description}", f"# TYPE {self.name} counter"]
        with self._lock:
            for label_key, value in self._values.items():
                if label_key:
                    lines.append(f"{self.name}{{{label_key}}} {value}")
                else:
                    lines.append(f"{self.name} {value}")
        return "\n".join(lines)


class Gauge:
    """
    Metric that can go up and down.

    Usage:
        balance = Gauge("account_balance", "Current account balance")
        balance.set(1000.0)
        balance.inc(50.0)
        balance.dec(25.0)
    """

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self._values: Dict[str, float] = defaultdict(float)
        self._lock = Lock()

    def set(self, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Set gauge value."""
        label_key = self._labels_to_key(labels)
        with self._lock:
            self._values[label_key] = value

    def inc(self, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        """Increment gauge."""
        label_key = self._labels_to_key(labels)
        with self._lock:
            self._values[label_key] += value

    def dec(self, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        """Decrement gauge."""
        label_key = self._labels_to_key(labels)
        with self._lock:
            self._values[label_key] -= value

    def get(self, labels: Optional[Dict[str, str]] = None) -> float:
        """Get current gauge value."""
        label_key = self._labels_to_key(labels)
        with self._lock:
            return self._values[label_key]

    def _labels_to_key(self, labels: Optional[Dict[str, str]]) -> str:
        if not labels:
            return ""
        return ",".join(f"{k}={v}" for k, v in sorted(labels.items()))

    def to_prometheus(self) -> str:
        """Export in Prometheus format."""
        lines = [f"# HELP {self.name} {self.description}", f"# TYPE {self.name} gauge"]
        with self._lock:
            for label_key, value in self._values.items():
                if label_key:
                    lines.append(f"{self.name}{{{label_key}}} {value}")
                else:
                    lines.append(f"{self.name} {value}")
        return "\n".join(lines)


class Histogram:
    """
    Histogram metric for measuring distributions.

    Usage:
        latency = Histogram("request_latency_seconds", "Request latency")
        with latency.time():
            do_something()
    """

    DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

    def __init__(
        self,
        name: str,
        description: str = "",
        buckets: tuple = DEFAULT_BUCKETS,
    ):
        self.name = name
        self.description = description
        self.buckets = sorted(buckets)
        self._counts: Dict[str, Dict[float, int]] = defaultdict(lambda: defaultdict(int))
        self._sums: Dict[str, float] = defaultdict(float)
        self._count: Dict[str, int] = defaultdict(int)
        self._lock = Lock()

    def observe(self, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Record an observation."""
        label_key = self._labels_to_key(labels)
        with self._lock:
            self._sums[label_key] += value
            self._count[label_key] += 1
            for bucket in self.buckets:
                if value <= bucket:
                    self._counts[label_key][bucket] += 1

    def time(self, labels: Optional[Dict[str, str]] = None):
        """Context manager to time a block of code."""
        return _HistogramTimer(self, labels)

    def _labels_to_key(self, labels: Optional[Dict[str, str]]) -> str:
        if not labels:
            return ""
        return ",".join(f"{k}={v}" for k, v in sorted(labels.items()))

    def to_prometheus(self) -> str:
        """Export in Prometheus format."""
        lines = [f"# HELP {self.name} {self.description}", f"# TYPE {self.name} histogram"]
        with self._lock:
            for label_key in set(list(self._counts.keys()) + list(self._sums.keys())):
                label_suffix = f"{{{label_key}}}" if label_key else ""

                # Bucket counts
                cumulative = 0
                for bucket in self.buckets:
                    cumulative += self._counts[label_key].get(bucket, 0)
                    if label_key:
                        lines.append(
                            f'{self.name}_bucket{{le="{bucket}",{label_key}}} {cumulative}'
                        )
                    else:
                        lines.append(f'{self.name}_bucket{{le="{bucket}"}} {cumulative}')

                # +Inf bucket
                if label_key:
                    lines.append(
                        f'{self.name}_bucket{{le="+Inf",{label_key}}} {self._count[label_key]}'
                    )
                else:
                    lines.append(f'{self.name}_bucket{{le="+Inf"}} {self._count[label_key]}')

                # Sum and count
                lines.append(f"{self.name}_sum{label_suffix} {self._sums[label_key]}")
                lines.append(f"{self.name}_count{label_suffix} {self._count[label_key]}")

        return "\n".join(lines)


class _HistogramTimer:
    """Context manager for timing histogram observations."""

    def __init__(self, histogram: Histogram, labels: Optional[Dict[str, str]]):
        self.histogram = histogram
        self.labels = labels
        self.start_time: float = 0

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, *args):
        duration = time.perf_counter() - self.start_time
        self.histogram.observe(duration, self.labels)


class MetricsRegistry:
    """
    Central registry for all metrics.

    Usage:
        registry = MetricsRegistry()

        # Create metrics
        requests = registry.counter("requests_total", "Total requests")
        balance = registry.gauge("balance", "Current balance")

        # Export all
        print(registry.to_prometheus())
    """

    def __init__(self):
        self._counters: Dict[str, Counter] = {}
        self._gauges: Dict[str, Gauge] = {}
        self._histograms: Dict[str, Histogram] = {}
        self._lock = Lock()

    def counter(self, name: str, description: str = "") -> Counter:
        """Get or create a counter."""
        with self._lock:
            if name not in self._counters:
                self._counters[name] = Counter(name, description)
            return self._counters[name]

    def gauge(self, name: str, description: str = "") -> Gauge:
        """Get or create a gauge."""
        with self._lock:
            if name not in self._gauges:
                self._gauges[name] = Gauge(name, description)
            return self._gauges[name]

    def histogram(
        self,
        name: str,
        description: str = "",
        buckets: tuple = Histogram.DEFAULT_BUCKETS,
    ) -> Histogram:
        """Get or create a histogram."""
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = Histogram(name, description, buckets)
            return self._histograms[name]

    def to_prometheus(self) -> str:
        """Export all metrics in Prometheus format."""
        lines = []
        with self._lock:
            for counter in self._counters.values():
                lines.append(counter.to_prometheus())
            for gauge in self._gauges.values():
                lines.append(gauge.to_prometheus())
            for histogram in self._histograms.values():
                lines.append(histogram.to_prometheus())
        return "\n\n".join(lines)

    def get_all_stats(self) -> Dict[str, Any]:
        """Get all metrics as a dictionary."""
        stats = {"counters": {}, "gauges": {}, "histograms": {}}
        with self._lock:
            for name, counter in self._counters.items():
                stats["counters"][name] = dict(counter._values)
            for name, gauge in self._gauges.items():
                stats["gauges"][name] = dict(gauge._values)
            for name, histogram in self._histograms.items():
                stats["histograms"][name] = {
                    "sum": dict(histogram._sums),
                    "count": dict(histogram._count),
                }
        return stats


# Global metrics registry
_registry: Optional[MetricsRegistry] = None


def get_metrics_registry() -> MetricsRegistry:
    """Get the global metrics registry."""
    global _registry
    if _registry is None:
        _registry = MetricsRegistry()
    return _registry


# Pre-defined metrics for the trading bot
def get_trading_metrics() -> Dict[str, Any]:
    """Get pre-defined trading metrics."""
    registry = get_metrics_registry()

    return {
        # API metrics
        "api_requests": registry.counter("pp_api_requests_total", "Total API requests"),
        "api_errors": registry.counter("pp_api_errors_total", "Total API errors"),
        "api_latency": registry.histogram(
            "pp_api_latency_seconds",
            "API request latency",
            buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
        ),
        # Trading metrics
        "trades_total": registry.counter("pp_trades_total", "Total trades executed"),
        "trades_volume": registry.counter("pp_trades_volume_usd", "Total trading volume in USD"),
        "decisions": registry.counter("pp_decisions_total", "Total trading decisions"),
        # Portfolio metrics
        "balance": registry.gauge("pp_balance_usd", "Current balance in USD"),
        "positions": registry.gauge("pp_positions_count", "Number of open positions"),
        "exposure": registry.gauge("pp_exposure_pct", "Current exposure percentage"),
        "daily_pnl": registry.gauge("pp_daily_pnl_usd", "Daily P&L in USD"),
        # Agent metrics
        "agent_loops": registry.counter("pp_agent_loops_total", "Total agent loop iterations"),
        "agent_errors": registry.counter("pp_agent_errors_total", "Total agent errors"),
        # WebSocket metrics
        "ws_messages": registry.counter("pp_websocket_messages_total", "Total WebSocket messages"),
        "ws_reconnects": registry.counter(
            "pp_websocket_reconnects_total", "WebSocket reconnections"
        ),
    }


def record_api_request(
    endpoint: str,
    method: str,
    status: str,
    duration: float,
) -> None:
    """Record an API request metric."""
    metrics = get_trading_metrics()
    labels = {"endpoint": endpoint, "method": method, "status": status}

    metrics["api_requests"].inc(labels=labels)
    if status.startswith("5") or status == "error":
        metrics["api_errors"].inc(labels=labels)
    metrics["api_latency"].observe(duration, labels={"endpoint": endpoint})


def record_trade(
    side: str,
    size: float,
    platform: str = "polymarket",
) -> None:
    """Record a trade metric."""
    metrics = get_trading_metrics()
    labels = {"side": side, "platform": platform}

    metrics["trades_total"].inc(labels=labels)
    metrics["trades_volume"].inc(size, labels=labels)


def update_portfolio_metrics(
    balance: float,
    positions: int,
    exposure: float,
    daily_pnl: float,
) -> None:
    """Update portfolio gauge metrics."""
    metrics = get_trading_metrics()

    metrics["balance"].set(balance)
    metrics["positions"].set(positions)
    metrics["exposure"].set(exposure)
    metrics["daily_pnl"].set(daily_pnl)
