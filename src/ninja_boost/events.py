"""
ninja_boost.events
~~~~~~~~~~~~~~~~~~
A lightweight synchronous and asynchronous event bus.

Every component in ninja_boost fires events at well-defined points in the
request lifecycle. You can subscribe to any event from your application code
without modifying framework internals.

Built-in events
---------------
    before_request          fired before a view is called
    after_response          fired after a response is created
    on_error                fired when an unhandled exception occurs
    on_auth_failure         fired when authentication fails (returns None)
    on_rate_limit_exceeded  fired when a rate limit is breached
    on_permission_denied    fired when a permission check fails
    on_policy_denied        fired when a policy evaluation returns False
    on_service_registered   fired when a service is registered in the registry
    on_plugin_loaded        fired when a plugin is registered

Usage::

    from ninja_boost.events import event_bus

    @event_bus.on("before_request")
    def log_incoming(request, ctx, **kw):
        print(f"[{ctx['trace_id']}] {request.method} {request.path}")

    @event_bus.on("after_response")
    def record_timing(request, ctx, response, duration_ms, **kw):
        print(f"→ {response.status_code}  {duration_ms:.1f}ms")

Async handlers::

    @event_bus.on("before_request")
    async def async_handler(request, ctx, **kw):
        await some_async_operation()

    # Then emit async:
    await event_bus.emit_async("before_request", request=request, ctx=ctx)
"""

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable

logger = logging.getLogger("ninja_boost.events")

# ── Built-in event names (use these as constants to avoid typos) ───────────
BEFORE_REQUEST         = "before_request"
AFTER_RESPONSE         = "after_response"
ON_ERROR               = "on_error"
ON_AUTH_FAILURE        = "on_auth_failure"
ON_RATE_LIMIT_EXCEEDED = "on_rate_limit_exceeded"
ON_PERMISSION_DENIED   = "on_permission_denied"
ON_POLICY_DENIED       = "on_policy_denied"
ON_SERVICE_REGISTERED  = "on_service_registered"
ON_PLUGIN_LOADED       = "on_plugin_loaded"


class EventBus:
    """
    Central pub/sub event bus.

    Thread-safe for registration; emission is sequential per-event.
    Supports both sync and async handlers via emit / emit_async.
    """

    def __init__(self):
        self._handlers: dict[str, list[Callable]] = defaultdict(list)
        self._wildcard: list[Callable] = []

    # ── Registration ───────────────────────────────────────────────────────

    def on(self, event: str):
        """
        Decorator: register a handler for *event*.

        The handler receives ``**kwargs`` matching what the emitter passes.
        Use ``**kw`` to absorb unknown fields — events may gain new fields
        in future versions without breaking existing handlers.

        Example::

            @event_bus.on("before_request")
            def my_handler(request, ctx, **kw):
                ...
        """
        def decorator(fn: Callable) -> Callable:
            self._handlers[event].append(fn)
            logger.debug("Registered handler %s for event '%s'", fn.__qualname__, event)
            return fn
        return decorator

    def on_any(self, fn: Callable) -> Callable:
        """Register *fn* as a wildcard handler that receives every event."""
        self._wildcard.append(fn)
        return fn

    def off(self, event: str, fn: Callable) -> None:
        """Remove a previously registered handler."""
        self._handlers[event] = [h for h in self._handlers[event] if h is not fn]

    def clear(self, event: str | None = None) -> None:
        """Remove all handlers for *event*, or all handlers if event is None."""
        if event is None:
            self._handlers.clear()
            self._wildcard.clear()
        else:
            self._handlers[event] = []

    # ── Emission ──────────────────────────────────────────────────────────

    def emit(self, event: str, **kwargs: Any) -> None:
        """
        Fire *event* synchronously, calling all registered handlers in order.

        Exceptions raised by handlers are logged and swallowed so they cannot
        crash the main request cycle.
        """
        for handler in self._handlers.get(event, []) + self._wildcard:
            try:
                if asyncio.iscoroutinefunction(handler):
                    # Schedule async handlers from synchronous emit().
                    # get_running_loop() raises RuntimeError if there is no
                    # running loop in this thread, which is the common case
                    # when emit() is called from Django's sync request cycle.
                    try:
                        loop = asyncio.get_running_loop()
                        # There IS a running loop (e.g. ASGI / async test) —
                        # schedule the coroutine on it; fire-and-forget.
                        loop.create_task(handler(event=event, **kwargs))
                    except RuntimeError:
                        # No running loop — safe to call asyncio.run().
                        asyncio.run(handler(event=event, **kwargs))
                else:
                    handler(event=event, **kwargs)
            except Exception:
                logger.exception(
                    "Handler %s raised during event '%s'",
                    getattr(handler, "__qualname__", repr(handler)),
                    event,
                )

    async def emit_async(self, event: str, **kwargs: Any) -> None:
        """
        Fire *event* asynchronously, awaiting all async handlers concurrently
        and calling sync handlers sequentially first.
        """
        sync_handlers  = []
        async_handlers = []

        for h in self._handlers.get(event, []) + self._wildcard:
            (async_handlers if asyncio.iscoroutinefunction(h) else sync_handlers).append(h)

        for handler in sync_handlers:
            try:
                handler(event=event, **kwargs)
            except Exception:
                logger.exception("Sync handler %s raised during async emit '%s'",
                                 getattr(handler, "__qualname__", repr(handler)), event)

        if async_handlers:
            results = await asyncio.gather(
                *[h(event=event, **kwargs) for h in async_handlers],
                return_exceptions=True,
            )
            for result, handler in zip(results, async_handlers):
                if isinstance(result, Exception):
                    logger.exception("Async handler %s raised during emit '%s'",
                                     getattr(handler, "__qualname__", repr(handler)), event,
                                     exc_info=result)

    def listeners(self, event: str) -> list[Callable]:
        """Return all handlers registered for *event*."""
        return list(self._handlers.get(event, []))

    def events(self) -> list[str]:
        """Return all event names that have at least one handler."""
        return [k for k, v in self._handlers.items() if v]


# ── Global singleton ──────────────────────────────────────────────────────
event_bus = EventBus()
