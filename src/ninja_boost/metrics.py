"""
ninja_boost.metrics
~~~~~~~~~~~~~~~~~~~~
Metrics hooks with pluggable backends.

ninja_boost emits timing, error, and throughput metrics at key lifecycle
points. You plug in the backend (Prometheus, StatsD, Datadog, CloudWatch,
or a custom callable). No backend is active by default — zero overhead
unless you opt in.

Built-in backends
-----------------
    PrometheusBackend     — integrates with django-prometheus or prometheus_client
    StatsDBackend         — sends UDP metrics to any StatsD-compatible server
    DatadogBackend        — uses the datadog Python client
    LoggingBackend        — writes metrics to the Python logging system (dev/test)

Activation via settings::

    NINJA_BOOST = {
        ...
        "METRICS": {
            "BACKEND": "ninja_boost.metrics.PrometheusBackend",
            # Backend-specific options:
            "NAMESPACE": "myapi",       # prefix for all metric names
        },
    }

Or programmatically::

    from ninja_boost.metrics import metrics, PrometheusBackend
    metrics.use(PrometheusBackend(namespace="myapi"))

Emitted metrics
---------------
    {ns}_request_total            counter   — total requests (labels: method, path, status)
    {ns}_request_duration_seconds histogram — response time (labels: method, path)
    {ns}_request_errors_total     counter   — 4xx/5xx responses
    {ns}_rate_limit_hits_total    counter   — rate limit rejections (label: path)
    {ns}_permission_denied_total  counter   — permission/policy denials (label: path)
    {ns}_active_requests          gauge     — currently in-flight requests

Custom metrics::

    from ninja_boost.metrics import metrics

    @router.post("/checkout")
    def checkout(request, ctx, payload):
        result = OrderService.checkout(payload)
        metrics.increment("orders_created", labels={"tier": ctx["user"]["tier"]})
        metrics.timing("checkout_ms", result.duration_ms)
        return result
"""

import logging
import threading
import time
from collections.abc import Callable
from functools import wraps
from typing import Any

logger = logging.getLogger("ninja_boost.metrics")


# ── Base backend ──────────────────────────────────────────────────────────

class BaseMetricsBackend:
    """Implement this interface to plug in any metrics system."""

    def increment(self, name: str, value: int = 1, labels: dict | None = None) -> None:
        """Increment a counter metric."""

    def decrement(self, name: str, value: int = 1, labels: dict | None = None) -> None:
        """Decrement a counter metric."""

    def gauge(self, name: str, value: float, labels: dict | None = None) -> None:
        """Set an absolute gauge value."""

    def timing(self, name: str, value_ms: float, labels: dict | None = None) -> None:
        """Record a timing/duration metric (milliseconds)."""

    def histogram(self, name: str, value: float, labels: dict | None = None) -> None:
        """Record a value in a histogram."""


# ── Logging backend (zero dependencies, always available) ─────────────────

class LoggingBackend(BaseMetricsBackend):
    """
    Writes metrics to Python logging. Useful for development and testing.
    No external dependencies.
    """
    _log = logging.getLogger("ninja_boost.metrics.log")

    def __init__(self, level: int = logging.DEBUG):
        self._level = level

    def _emit(self, kind: str, name: str, value: Any, labels: dict | None) -> None:
        self._log.log(self._level, "metric %s %s=%s labels=%s", kind, name, value, labels or {})

    def increment(self, name, value=1, labels=None):
        self._emit("counter++", name, value, labels)

    def decrement(self, name, value=1, labels=None):
        self._emit("counter--", name, value, labels)

    def gauge(self, name, value, labels=None):
        self._emit("gauge", name, value, labels)

    def timing(self, name, value_ms, labels=None):
        self._emit("timing", name, f"{value_ms:.2f}ms", labels)

    def histogram(self, name, value, labels=None):
        self._emit("hist", name, value, labels)


# ── Prometheus backend ────────────────────────────────────────────────────

class PrometheusBackend(BaseMetricsBackend):
    """
    Prometheus metrics via ``prometheus_client``.

    Install::
        pip install prometheus_client

    Then expose metrics in urls.py::
        from django.urls import path
        from prometheus_client import make_wsgi_app
        from django.core.handlers.wsgi import WSGIHandler

        # Or use django-prometheus which handles routing automatically.
    """

    def __init__(self, namespace: str = "ninja_boost"):
        try:
            import prometheus_client as prom
        except ImportError as exc:
            raise ImportError(
                "PrometheusBackend requires prometheus_client. "
                "Install it with: pip install prometheus_client"
            ) from exc
        self._prom = prom
        self._ns   = namespace
        self._counters:    dict = {}
        self._gauges:      dict = {}
        self._histograms:  dict = {}
        self._lock = threading.Lock()

    def _counter(self, name: str, label_names: list) -> Any:
        key = (name, tuple(label_names))
        if key not in self._counters:
            with self._lock:
                if key not in self._counters:
                    self._counters[key] = self._prom.Counter(
                        f"{self._ns}_{name}", name, label_names
                    )
        return self._counters[key]

    def _gauge_metric(self, name: str, label_names: list) -> Any:
        key = (name, tuple(label_names))
        if key not in self._gauges:
            with self._lock:
                if key not in self._gauges:
                    self._gauges[key] = self._prom.Gauge(
                        f"{self._ns}_{name}", name, label_names
                    )
        return self._gauges[key]

    def _histogram_metric(self, name: str, label_names: list) -> Any:
        key = (name, tuple(label_names))
        if key not in self._histograms:
            with self._lock:
                if key not in self._histograms:
                    self._histograms[key] = self._prom.Histogram(
                        f"{self._ns}_{name}", name, label_names
                    )
        return self._histograms[key]

    def increment(self, name, value=1, labels=None):
        label_names = list(labels.keys()) if labels else []
        label_vals  = list(labels.values()) if labels else []
        c = self._counter(name, label_names)
        (c.labels(*label_vals) if label_vals else c).inc(value)

    def gauge(self, name, value, labels=None):
        label_names = list(labels.keys()) if labels else []
        label_vals  = list(labels.values()) if labels else []
        g = self._gauge_metric(name, label_names)
        (g.labels(*label_vals) if label_vals else g).set(value)

    def timing(self, name, value_ms, labels=None):
        self.histogram(name + "_ms", value_ms, labels)

    def histogram(self, name, value, labels=None):
        label_names = list(labels.keys()) if labels else []
        label_vals  = list(labels.values()) if labels else []
        h = self._histogram_metric(name, label_names)
        (h.labels(*label_vals) if label_vals else h).observe(value)

    def decrement(self, name, value=1, labels=None):
        self.increment(name, -value, labels)


# ── StatsD backend ────────────────────────────────────────────────────────

class StatsDBackend(BaseMetricsBackend):
    """
    StatsD UDP metrics backend.

    Compatible with StatsD, Telegraf, Datadog Agent (DogStatsD), and
    any StatsD-protocol server.

    Install::
        pip install statsd

    Usage::
        NINJA_BOOST = {
            "METRICS": {
                "BACKEND": "ninja_boost.metrics.StatsDBackend",
                "HOST": "localhost",
                "PORT": 8125,
                "PREFIX": "myapi",
            }
        }
    """

    def __init__(self, host: str = "localhost", port: int = 8125,
                 prefix: str = "ninja_boost"):
        try:
            import statsd
            self._client = statsd.StatsClient(host, port, prefix=prefix)
        except ImportError as exc:
            raise ImportError(
                "StatsDBackend requires statsd. Install with: pip install statsd"
            ) from exc

    def _key(self, name: str, labels: dict | None) -> str:
        if not labels:
            return name
        suffix = ".".join(f"{k}_{v}" for k, v in sorted(labels.items()))
        return f"{name}.{suffix}"

    def increment(self, name, value=1, labels=None):
        self._client.incr(self._key(name, labels), value)

    def decrement(self, name, value=1, labels=None):
        self._client.decr(self._key(name, labels), value)

    def gauge(self, name, value, labels=None):
        self._client.gauge(self._key(name, labels), value)

    def timing(self, name, value_ms, labels=None):
        self._client.timing(self._key(name, labels), value_ms)

    def histogram(self, name, value, labels=None):
        self._client.timing(self._key(name, labels), value)  # StatsD uses timing for histograms


# ── Datadog backend ───────────────────────────────────────────────────────

class DatadogBackend(BaseMetricsBackend):
    """
    Datadog metrics backend via the ``datadog`` Python client.

    Install::
        pip install datadog

    Usage::
        NINJA_BOOST = {
            "METRICS": {
                "BACKEND": "ninja_boost.metrics.DatadogBackend",
                "PREFIX": "myapi",
                "HOST": "localhost",   # DogStatsD agent host (default: localhost)
                "PORT": 8125,          # DogStatsD agent port (default: 8125)
            }
        }
    """

    def __init__(self, prefix: str = "ninja_boost",
                 host: str = "localhost", port: int = 8125):
        try:
            from datadog import initialize, statsd as dd_statsd  # noqa: I001
            initialize(statsd_host=host, statsd_port=port)
            self._statsd = dd_statsd
        except ImportError as exc:
            raise ImportError(
                "DatadogBackend requires the datadog package. "
                "Install it with: pip install datadog"
            ) from exc
        self._prefix = prefix

    def _key(self, name: str, labels: dict | None) -> str:
        key = f"{self._prefix}.{name}" if self._prefix else name
        return key

    def _tags(self, labels: dict | None) -> list:
        if not labels:
            return []
        return [f"{k}:{v}" for k, v in labels.items()]

    def increment(self, name, value=1, labels=None):
        self._statsd.increment(self._key(name, labels), value, tags=self._tags(labels))

    def decrement(self, name, value=1, labels=None):
        self._statsd.decrement(self._key(name, labels), value, tags=self._tags(labels))

    def gauge(self, name, value, labels=None):
        self._statsd.gauge(self._key(name, labels), value, tags=self._tags(labels))

    def timing(self, name, value_ms, labels=None):
        self._statsd.timing(self._key(name, labels), value_ms, tags=self._tags(labels))

    def histogram(self, name, value, labels=None):
        self._statsd.histogram(self._key(name, labels), value, tags=self._tags(labels))


# ── Metrics facade ────────────────────────────────────────────────────────

class Metrics:
    """
    Global metrics facade. All code calls this; backends are swappable.

    Usage::

        from ninja_boost.metrics import metrics
        metrics.increment("items_created")
        metrics.timing("db_query_ms", 12.4)

    Metrics are no-ops until a backend is configured.
    """

    def __init__(self):
        self._backend: BaseMetricsBackend | None = None
        self._active_requests = 0
        self._lock = threading.Lock()

    def use(self, backend: BaseMetricsBackend) -> None:
        """Set the active metrics backend."""
        self._backend = backend
        logger.info("Metrics backend set to %s", type(backend).__name__)

    def _get_backend(self) -> BaseMetricsBackend | None:
        if self._backend is not None:
            return self._backend
        # Lazy load from settings on first call
        from django.conf import settings
        from django.utils.module_loading import import_string
        cfg = getattr(settings, "NINJA_BOOST", {})
        mc  = cfg.get("METRICS", {})
        dotted = mc.get("BACKEND")
        if dotted:
            try:
                import inspect
                cls = import_string(dotted)
                ns  = mc.get("NAMESPACE") or mc.get("PREFIX", "ninja_boost")
                # Pass the configured namespace/prefix to the backend constructor.
                # PrometheusBackend/LoggingBackend use "namespace="; StatsDBackend uses "prefix=".
                try:
                    params = inspect.signature(cls.__init__).parameters
                except (ValueError, TypeError):
                    params = {}
                if "namespace" in params:
                    self._backend = cls(namespace=ns)
                elif "prefix" in params:
                    self._backend = cls(prefix=ns)
                else:
                    self._backend = cls()
            except Exception:
                logger.exception("Failed to load metrics backend '%s'", dotted)
        return self._backend

    def increment(self, name: str, value: int = 1, labels: dict | None = None) -> None:
        b = self._get_backend()
        if b:
            try:
                b.increment(name, value, labels)
            except Exception:
                logger.debug("metrics.increment failed", exc_info=True)

    def decrement(self, name: str, value: int = 1, labels: dict | None = None) -> None:
        b = self._get_backend()
        if b:
            try:
                b.decrement(name, value, labels)
            except Exception:
                logger.debug("metrics.decrement failed", exc_info=True)

    def gauge(self, name: str, value: float, labels: dict | None = None) -> None:
        b = self._get_backend()
        if b:
            try:
                b.gauge(name, value, labels)
            except Exception:
                logger.debug("metrics.gauge failed", exc_info=True)

    def timing(self, name: str, value_ms: float, labels: dict | None = None) -> None:
        b = self._get_backend()
        if b:
            try:
                b.timing(name, value_ms, labels)
            except Exception:
                logger.debug("metrics.timing failed", exc_info=True)

    def histogram(self, name: str, value: float, labels: dict | None = None) -> None:
        b = self._get_backend()
        if b:
            try:
                b.histogram(name, value, labels)
            except Exception:
                logger.debug("metrics.histogram failed", exc_info=True)

    def track_request_start(self) -> None:
        with self._lock:
            self._active_requests += 1
        self.gauge("active_requests", self._active_requests)

    def track_request_end(self, method: str, path: str, status: int, duration_ms: float) -> None:
        with self._lock:
            self._active_requests = max(0, self._active_requests - 1)
        self.gauge("active_requests", self._active_requests)
        labels = {"method": method, "path": _normalize_path(path), "status": str(status)}
        self.increment("request_total", labels=labels)
        self.timing("request_duration_ms", duration_ms,
                    labels={"method": method, "path": _normalize_path(path)})
        if status >= 400:
            self.increment(
                "request_errors_total",
                labels={"method": method, "path": _normalize_path(path), "status": str(status)},
            )

    def timer(self, name: str, labels: dict | None = None):
        """Context manager that records elapsed time."""
        return _Timer(self, name, labels)


def _normalize_path(path: str) -> str:
    """Replace numeric path segments with {id} to avoid cardinality explosion."""
    import re
    return re.sub(r"/\d+", "/{id}", path)


class _Timer:
    """Context manager returned by metrics.timer()."""
    def __init__(self, m: Metrics, name: str, labels: dict | None):
        self._m, self._name, self._labels = m, name, labels

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_):
        elapsed_ms = (time.perf_counter() - self._start) * 1000
        self._m.timing(self._name, elapsed_ms, self._labels)


# ── Global singleton ──────────────────────────────────────────────────────
metrics = Metrics()


# ── Decorator ─────────────────────────────────────────────────────────────

def track(name: str | None = None, labels: dict | None = None):
    """
    Decorator: record call count and execution time for a function.

    Example::

        @router.get("/items")
        @track("list_items")
        def list_items(request, ctx): ...
    """
    def decorator(func: Callable) -> Callable:
        import asyncio as _asyncio
        metric_name = name or f"{func.__module__}.{func.__qualname__}".replace(".", "_")

        if _asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                metrics.increment(f"{metric_name}_calls", labels=labels)
                with metrics.timer(f"{metric_name}_duration_ms", labels=labels):
                    return await func(*args, **kwargs)
            return async_wrapper

        @wraps(func)
        def wrapper(*args, **kwargs):
            metrics.increment(f"{metric_name}_calls", labels=labels)
            with metrics.timer(f"{metric_name}_duration_ms", labels=labels):
                return func(*args, **kwargs)
        return wrapper
    return decorator
