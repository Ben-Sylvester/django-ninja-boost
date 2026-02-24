"""
ninja_boost.lifecycle
~~~~~~~~~~~~~~~~~~~~~
Global request lifecycle hooks — a single middleware that fires the full
before_request / after_response / on_error event sequence, integrating
events, metrics, structured logging, and plugin hooks in one place.

Architecture
------------
The lifecycle middleware sits between Django's middleware stack and the view.
It coordinates all cross-cutting concerns at the request/response boundary:

    Request →  bind log context
              fire before_request events (plugins, event_bus handlers)
              track metrics (active_requests gauge, request counter)
              ↓
    View executes
              ↓
    Response ← record timing
              fire after_response events
              update metrics
              set X-RateLimit-* headers
              write structured access log

Setup::

    MIDDLEWARE = [
        ...
        "ninja_boost.middleware.TracingMiddleware",          # sets trace_id
        "ninja_boost.lifecycle.LifecycleMiddleware",         # all lifecycle hooks
    ]

    # TracingMiddleware MUST come before LifecycleMiddleware.
    # LifecycleMiddleware replaces the need for StructuredLoggingMiddleware
    # — don't use both.

The lifecycle can also be used as a per-view decorator::

    from ninja_boost.lifecycle import lifecycle_hooks

    @router.get("/items", inject=False, paginate=False, auth=None)
    @lifecycle_hooks
    def health(request):
        return {"status": "ok"}
"""

import logging
import time
from functools import wraps
from typing import Any, Callable

logger = logging.getLogger("ninja_boost.lifecycle")


class LifecycleMiddleware:
    """
    WSGI + ASGI compatible middleware that fires the complete ninja_boost
    event lifecycle on every request.

    Integrates:
      - Structured log context binding (trace_id, method, path, user_id)
      - before_request / after_response / on_error event bus emissions
      - Plugin hook dispatch
      - Metrics: active_requests gauge, request counter, duration histogram
      - X-RateLimit-* response headers (if rate limit info is on request)
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

    # ── Sync path ──────────────────────────────────────────────────────────

    def _sync_call(self, request):
        ctx = _build_ctx(request)
        _before(request, ctx)
        start = time.perf_counter()

        try:
            response = self.get_response(request)
        except Exception as exc:
            _on_error(request, ctx, exc)
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        _after(request, ctx, response, duration_ms)
        return response

    # ── Async path ────────────────────────────────────────────────────────

    async def __acall__(self, request):
        ctx = _build_ctx(request)
        _before(request, ctx)
        start = time.perf_counter()

        try:
            response = await self.get_response(request)
        except Exception as exc:
            _on_error(request, ctx, exc)
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        _after(request, ctx, response, duration_ms)
        return response


# ── Shared lifecycle helpers ──────────────────────────────────────────────

def _build_ctx(request) -> dict:
    """Build the context dict available in lifecycle events."""
    from ninja_boost.dependencies import _client_ip
    return {
        "user":     getattr(request, "auth", None),
        "ip":       _client_ip(request),
        "trace_id": getattr(request, "trace_id", None),
    }


def _before(request, ctx: dict) -> None:
    """Fire all before_request hooks."""
    # 1. Bind structured log context
    try:
        from ninja_boost.logging_structured import bind_request_context
        bind_request_context(request, ctx)
    except Exception:
        pass

    # 2. Track active request (metrics)
    try:
        from ninja_boost.metrics import metrics
        metrics.track_request_start()
    except Exception:
        pass

    # 3. Fire event bus
    try:
        from ninja_boost.events import event_bus, BEFORE_REQUEST
        event_bus.emit(BEFORE_REQUEST, request=request, ctx=ctx)
    except Exception:
        logger.exception("before_request event raised")


def _after(request, ctx: dict, response, duration_ms: float) -> None:
    """Fire all after_response hooks and attach diagnostic headers."""
    # 1. Set X-RateLimit headers if info was attached by rate_limit decorator
    try:
        if hasattr(request, "rate_limit_limit"):
            response["X-RateLimit-Limit"]     = str(request.rate_limit_limit)
            response["X-RateLimit-Remaining"] = str(getattr(request, "rate_limit_remaining", 0))
    except Exception:
        pass

    # 2. Update metrics
    try:
        from ninja_boost.metrics import metrics
        metrics.track_request_end(
            method=getattr(request, "method", "?"),
            path=getattr(request, "path", "/"),
            status=getattr(response, "status_code", 200),
            duration_ms=duration_ms,
        )
    except Exception:
        pass

    # 3. Fire event bus
    try:
        from ninja_boost.events import event_bus, AFTER_RESPONSE
        event_bus.emit(
            AFTER_RESPONSE,
            request=request,
            ctx=ctx,
            response=response,
            duration_ms=duration_ms,
        )
    except Exception:
        logger.exception("after_response event raised")

    # 4. Write structured access log
    try:
        from ninja_boost.logging_structured import request_logger, clear_request_context
        request_logger.log_response(request, response, duration_ms)
        clear_request_context()
    except Exception:
        pass


def _on_error(request, ctx: dict, exc: Exception) -> None:
    """Fire on_error event bus hooks."""
    try:
        from ninja_boost.events import event_bus, ON_ERROR
        event_bus.emit(ON_ERROR, request=request, ctx=ctx, exc=exc)
    except Exception:
        logger.exception("on_error event raised")

    # Update error metrics
    try:
        from ninja_boost.metrics import metrics
        metrics.increment("unhandled_errors_total", labels={
            "error_type": type(exc).__name__,
        })
    except Exception:
        pass


# ── Per-view decorator variant ────────────────────────────────────────────

def lifecycle_hooks(func: Callable) -> Callable:
    """
    Decorator: apply lifecycle hooks to a single view without middleware.

    Useful for views outside the main API (webhooks, admin actions).
    """
    import asyncio

    if asyncio.iscoroutinefunction(func):
        @wraps(func)
        async def async_wrapper(request, *args, **kwargs) -> Any:
            ctx = _build_ctx(request)
            _before(request, ctx)
            start = time.perf_counter()
            try:
                result = await func(request, *args, **kwargs)
            except Exception as exc:
                _on_error(request, ctx, exc)
                raise
            duration_ms = (time.perf_counter() - start) * 1000
            # No response object available here — fire event with None
            from ninja_boost.events import event_bus, AFTER_RESPONSE
            event_bus.emit(AFTER_RESPONSE, request=request, ctx=ctx,
                           response=None, duration_ms=duration_ms)
            return result
        return async_wrapper

    @wraps(func)
    def sync_wrapper(request, *args, **kwargs) -> Any:
        ctx = _build_ctx(request)
        _before(request, ctx)
        start = time.perf_counter()
        try:
            result = func(request, *args, **kwargs)
        except Exception as exc:
            _on_error(request, ctx, exc)
            raise
        duration_ms = (time.perf_counter() - start) * 1000
        from ninja_boost.events import event_bus, AFTER_RESPONSE
        event_bus.emit(AFTER_RESPONSE, request=request, ctx=ctx,
                       response=None, duration_ms=duration_ms)
        return result
    return sync_wrapper
