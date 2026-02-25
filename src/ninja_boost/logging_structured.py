"""
ninja_boost.logging_structured
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Structured JSON logging that correlates log records with request context.

Every log record emitted during a request is automatically enriched with:
    - trace_id     from request.trace_id (set by TracingMiddleware)
    - method       HTTP method
    - path         request path
    - user_id      authenticated user ID (if available)
    - ip           client IP address
    - duration_ms  time taken to process the request (on after_response)

Activation
----------
Add to your Django LOGGING config in settings.py::

    import logging

    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": "ninja_boost.logging_structured.StructuredJsonFormatter",
            },
            "verbose": {
                "()": "ninja_boost.logging_structured.StructuredVerboseFormatter",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "json",     # swap to "verbose" for development
            },
        },
        "root": {"handlers": ["console"], "level": "INFO"},
        "loggers": {
            "ninja_boost": {"level": "DEBUG", "propagate": True},
            "django":      {"level": "WARNING", "propagate": True},
        },
    }

Context binding
---------------
Request-scoped context is bound via the context var system — every log
record from any logger during that request carries the bound fields.
No threadlocal hacks; works correctly with async views.

Manual context injection::

    from ninja_boost.logging_structured import bind_request_context

    @router.get("/items")
    def list_items(request, ctx):
        bind_request_context(request, ctx)     # already done by AutoRouter
        logger.info("fetching items")          # ← includes trace_id, user_id, etc.
        return ItemService.list()
"""

import json
import logging
import time
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

# ── Per-request context storage ───────────────────────────────────────────
_request_ctx: ContextVar[dict] = ContextVar("ninja_boost_log_ctx", default={})


def bind_request_context(request: Any, ctx: dict | None = None) -> None:
    """
    Bind request fields into the current context so all log records
    emitted during this request carry them automatically.
    """
    data: dict[str, Any] = {}
    data["trace_id"] = getattr(request, "trace_id", None)
    data["method"]   = getattr(request, "method", None)
    data["path"]     = getattr(request, "path", None)
    data["ip"]       = (ctx or {}).get("ip") or request.META.get("REMOTE_ADDR")

    user = (ctx or {}).get("user")
    if user is not None:
        if isinstance(user, dict):
            data["user_id"] = user.get("id") or user.get("user_id")
        else:
            data["user_id"] = getattr(user, "id", None)

    _request_ctx.set(data)


def get_request_context() -> dict:
    """Return the currently bound request context dict."""
    return _request_ctx.get({})


def clear_request_context() -> None:
    """Clear the request context (called at end of request lifecycle)."""
    _request_ctx.set({})


# ── JSON formatter ────────────────────────────────────────────────────────

class StructuredJsonFormatter(logging.Formatter):
    """
    Emits log records as single-line JSON objects.

    Every record includes the bound request context (trace_id, path, etc.)
    automatically. Output is suitable for ingestion by Datadog, CloudWatch
    Logs, Loki, or any JSON-aware log aggregator.

    Example output::

        {"timestamp": "2026-02-23T14:30:00.123Z", "level": "INFO",
         "logger": "apps.orders", "message": "Order created",
         "trace_id": "abc123", "method": "POST", "path": "/api/orders",
         "user_id": 42, "order_id": 7}
    """

    # Fields pulled from LogRecord that should NOT appear verbatim in the JSON
    _SKIP = frozenset({
        "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno",
        "funcName", "created", "msecs", "relativeCreated", "thread",
        "threadName", "processName", "process", "taskName",
        "name", "message",
    })

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()

        doc: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc)
                                 .strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "level":     record.levelname,
            "logger":    record.name,
            "message":   record.message,
        }

        # Merge bound request context
        doc.update(get_request_context())

        # Extra fields passed by caller: logger.info("msg", extra={"order_id": 7})
        for key, val in record.__dict__.items():
            if key not in self._SKIP and not key.startswith("_"):
                doc[key] = val

        # Exceptions
        if record.exc_info:
            doc["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            doc["stack"] = self.formatStack(record.stack_info)

        return json.dumps(doc, default=str, ensure_ascii=False)


class StructuredVerboseFormatter(logging.Formatter):
    """
    Human-readable formatter that still includes the structured context fields.
    Recommended for local development where JSON is hard to read.

    Example output::
        2026-02-23 14:30:00 INFO  [abc123] POST /api/orders — Order created
    """

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()
        ctx = get_request_context()
        trace  = ctx.get("trace_id", "")[:8] if ctx.get("trace_id") else "-"
        method = ctx.get("method", "")
        path   = ctx.get("path", "")
        ts     = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        line = f"{ts} {record.levelname:<7} [{trace}] {method} {path} — {record.message}"

        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


# ── Request timing logger ─────────────────────────────────────────────────

class RequestLogger:
    """
    Logs a structured record at the end of each request with timing info.

    Wire into the event bus::

        from ninja_boost.events import event_bus
        from ninja_boost.logging_structured import request_logger

        @event_bus.on("after_response")
        def log_request(request, ctx, response, duration_ms, **kw):
            request_logger.log_response(request, response, duration_ms)
    """

    _logger = logging.getLogger("ninja_boost.access")

    def log_response(self, request: Any, response: Any, duration_ms: float) -> None:
        status = getattr(response, "status_code", 0)
        level  = logging.WARNING if status >= 400 else logging.INFO
        self._logger.log(
            level,
            "%s %s → %s (%.1fms)",
            getattr(request, "method", "?"),
            getattr(request, "path", "?"),
            status,
            duration_ms,
            extra={
                "http_status":  status,
                "duration_ms":  round(duration_ms, 2),
                "http_method":  getattr(request, "method", None),
                "http_path":    getattr(request, "path", None),
            },
        )


request_logger = RequestLogger()


# ── Middleware integration ────────────────────────────────────────────────

class StructuredLoggingMiddleware:
    """
    Django middleware that:
      1. Binds request context into the context var on every request
      2. Times the request
      3. Logs a structured access record on completion

    Add *after* TracingMiddleware so request.trace_id is already set::

        MIDDLEWARE = [
            ...
            "ninja_boost.middleware.TracingMiddleware",
            "ninja_boost.logging_structured.StructuredLoggingMiddleware",
        ]
    """

    async_capable = True
    sync_capable  = True

    def __init__(self, get_response):
        import asyncio
        self.get_response = get_response
        self._is_async    = asyncio.iscoroutinefunction(get_response)

    def __call__(self, request):
        if self._is_async:
            return self.__acall__(request)
        return self._sync_call(request)

    def _sync_call(self, request):
        start = time.perf_counter()
        bind_request_context(request)
        response = self.get_response(request)
        duration_ms = (time.perf_counter() - start) * 1000
        request_logger.log_response(request, response, duration_ms)
        clear_request_context()
        return response

    async def __acall__(self, request):
        start = time.perf_counter()
        bind_request_context(request)
        response = await self.get_response(request)
        duration_ms = (time.perf_counter() - start) * 1000
        request_logger.log_response(request, response, duration_ms)
        clear_request_context()
        return response
