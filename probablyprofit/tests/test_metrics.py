"""
Tests for the metrics and observability module.
"""

import time

import pytest


class TestCounter:
    """Tests for Counter metric."""

    def test_increment_default(self):
        """Test incrementing counter by default value."""
        from probablyprofit.utils.metrics import Counter

        counter = Counter("test_counter", "Test counter")
        counter.inc()
        counter.inc()

        assert counter.get() == 2.0

    def test_increment_custom_value(self):
        """Test incrementing counter by custom value."""
        from probablyprofit.utils.metrics import Counter

        counter = Counter("test_counter")
        counter.inc(5.0)

        assert counter.get() == 5.0

    def test_increment_with_labels(self):
        """Test incrementing counter with labels."""
        from probablyprofit.utils.metrics import Counter

        counter = Counter("http_requests")
        counter.inc(labels={"method": "GET", "status": "200"})
        counter.inc(labels={"method": "POST", "status": "200"})
        counter.inc(labels={"method": "GET", "status": "200"})

        assert counter.get(labels={"method": "GET", "status": "200"}) == 2.0
        assert counter.get(labels={"method": "POST", "status": "200"}) == 1.0

    def test_reset(self):
        """Test resetting counter."""
        from probablyprofit.utils.metrics import Counter

        counter = Counter("test")
        counter.inc(10)
        counter.reset()

        assert counter.get() == 0.0

    def test_prometheus_format(self):
        """Test Prometheus export format."""
        from probablyprofit.utils.metrics import Counter

        counter = Counter("my_counter", "My test counter")
        counter.inc(5)

        output = counter.to_prometheus()

        assert "# HELP my_counter My test counter" in output
        assert "# TYPE my_counter counter" in output
        assert "my_counter 5" in output


class TestGauge:
    """Tests for Gauge metric."""

    def test_set_value(self):
        """Test setting gauge value."""
        from probablyprofit.utils.metrics import Gauge

        gauge = Gauge("temperature")
        gauge.set(42.5)

        assert gauge.get() == 42.5

    def test_inc_dec(self):
        """Test incrementing and decrementing gauge."""
        from probablyprofit.utils.metrics import Gauge

        gauge = Gauge("connections")
        gauge.set(10)
        gauge.inc(5)
        gauge.dec(3)

        assert gauge.get() == 12.0

    def test_with_labels(self):
        """Test gauge with labels."""
        from probablyprofit.utils.metrics import Gauge

        gauge = Gauge("balance")
        gauge.set(1000, labels={"account": "main"})
        gauge.set(500, labels={"account": "backup"})

        assert gauge.get(labels={"account": "main"}) == 1000
        assert gauge.get(labels={"account": "backup"}) == 500

    def test_prometheus_format(self):
        """Test Prometheus export format."""
        from probablyprofit.utils.metrics import Gauge

        gauge = Gauge("my_gauge", "My test gauge")
        gauge.set(100)

        output = gauge.to_prometheus()

        assert "# TYPE my_gauge gauge" in output
        assert "my_gauge 100" in output


class TestHistogram:
    """Tests for Histogram metric."""

    def test_observe(self):
        """Test recording observations."""
        from probablyprofit.utils.metrics import Histogram

        hist = Histogram("latency", buckets=(0.1, 0.5, 1.0))
        hist.observe(0.05)
        hist.observe(0.3)
        hist.observe(0.8)

        # Check internal state
        assert hist._count[""] == 3
        assert hist._sums[""] == pytest.approx(1.15, rel=0.01)

    def test_time_context_manager(self):
        """Test timing context manager."""
        from probablyprofit.utils.metrics import Histogram

        hist = Histogram("operation_duration")

        with hist.time():
            time.sleep(0.01)  # Sleep 10ms

        assert hist._count[""] == 1
        assert hist._sums[""] >= 0.01

    def test_prometheus_format(self):
        """Test Prometheus export format with buckets."""
        from probablyprofit.utils.metrics import Histogram

        hist = Histogram("request_duration", "Request duration", buckets=(0.1, 0.5))
        hist.observe(0.05)
        hist.observe(0.3)

        output = hist.to_prometheus()

        assert "# TYPE request_duration histogram" in output
        assert 'request_duration_bucket{le="0.1"}' in output
        assert 'request_duration_bucket{le="0.5"}' in output
        assert 'request_duration_bucket{le="+Inf"}' in output
        assert "request_duration_sum" in output
        assert "request_duration_count" in output


class TestMetricsRegistry:
    """Tests for MetricsRegistry."""

    def test_create_counter(self):
        """Test creating counter via registry."""
        from probablyprofit.utils.metrics import MetricsRegistry

        registry = MetricsRegistry()
        counter = registry.counter("requests", "Total requests")

        assert counter is not None
        counter.inc()
        assert counter.get() == 1.0

    def test_get_same_counter(self):
        """Test getting same counter returns existing instance."""
        from probablyprofit.utils.metrics import MetricsRegistry

        registry = MetricsRegistry()
        counter1 = registry.counter("requests")
        counter1.inc(5)

        counter2 = registry.counter("requests")

        assert counter1 is counter2
        assert counter2.get() == 5.0

    def test_create_gauge(self):
        """Test creating gauge via registry."""
        from probablyprofit.utils.metrics import MetricsRegistry

        registry = MetricsRegistry()
        gauge = registry.gauge("balance")

        gauge.set(1000)
        assert gauge.get() == 1000

    def test_create_histogram(self):
        """Test creating histogram via registry."""
        from probablyprofit.utils.metrics import MetricsRegistry

        registry = MetricsRegistry()
        hist = registry.histogram("latency", buckets=(0.1, 1.0))

        hist.observe(0.5)
        assert hist._count[""] == 1

    def test_prometheus_export_all(self):
        """Test exporting all metrics to Prometheus format."""
        from probablyprofit.utils.metrics import MetricsRegistry

        registry = MetricsRegistry()

        counter = registry.counter("requests")
        counter.inc()

        gauge = registry.gauge("connections")
        gauge.set(10)

        output = registry.to_prometheus()

        assert "requests" in output
        assert "connections" in output

    def test_get_all_stats(self):
        """Test getting all stats as dictionary."""
        from probablyprofit.utils.metrics import MetricsRegistry

        registry = MetricsRegistry()

        registry.counter("requests").inc(5)
        registry.gauge("balance").set(100)

        stats = registry.get_all_stats()

        assert "counters" in stats
        assert "gauges" in stats
        assert "histograms" in stats


class TestGlobalRegistry:
    """Tests for global registry functions."""

    def test_get_metrics_registry_singleton(self):
        """Test that get_metrics_registry returns singleton."""
        from probablyprofit.utils.metrics import get_metrics_registry

        registry1 = get_metrics_registry()
        registry2 = get_metrics_registry()

        assert registry1 is registry2

    def test_get_trading_metrics(self):
        """Test getting pre-defined trading metrics."""
        from probablyprofit.utils.metrics import get_trading_metrics

        metrics = get_trading_metrics()

        assert "api_requests" in metrics
        assert "trades_total" in metrics
        assert "balance" in metrics
        assert "positions" in metrics


class TestHelperFunctions:
    """Tests for helper recording functions."""

    def test_record_api_request(self):
        """Test recording API request."""
        from probablyprofit.utils.metrics import get_trading_metrics, record_api_request

        record_api_request("/api/markets", "GET", "200", 0.1)

        metrics = get_trading_metrics()
        # Just verify it doesn't raise
        assert metrics["api_requests"].get(
            labels={"endpoint": "/api/markets", "method": "GET", "status": "200"}
        ) >= 1

    def test_record_trade(self):
        """Test recording trade."""
        from probablyprofit.utils.metrics import get_trading_metrics, record_trade

        record_trade("BUY", 100.0, "polymarket")

        metrics = get_trading_metrics()
        assert metrics["trades_total"].get(
            labels={"side": "BUY", "platform": "polymarket"}
        ) >= 1

    def test_update_portfolio_metrics(self):
        """Test updating portfolio metrics."""
        from probablyprofit.utils.metrics import (get_trading_metrics,
                                                   update_portfolio_metrics)

        update_portfolio_metrics(
            balance=5000.0,
            positions=3,
            exposure=0.45,
            daily_pnl=150.0,
        )

        metrics = get_trading_metrics()
        assert metrics["balance"].get() == 5000.0
        assert metrics["positions"].get() == 3
        assert metrics["exposure"].get() == 0.45
        assert metrics["daily_pnl"].get() == 150.0
