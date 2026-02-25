"""
ninja_boost.middleware
~~~~~~~~~~~~~~~~~~~~~~
TracingMiddleware — stamps every request with a UUID trace ID and fires
the before_request / after_response event cycle.

The trace ID is:
  - Available as ``request.trace_id`` inside any view
  - Injected into ``ctx["trace_id"]`` by inject_context / AutoRouter
  - Returned in the ``X-Trace-Id`` response header for client/APM correlation

Setup (add to MIDDLEWARE in settings.py)::

    MIDDLEWARE = [
        ...
        "ninja_boost.middleware.TracingMiddleware",
        # Optional — adds structured access logging and full lifecycle hooks:
        # "ninja_boost.lifecycle.LifecycleMiddleware",
    ]
"""

import logging
import time
import uuid

logger = logging.getLogger("ninja_boost.tracing")


class TracingMiddleware:
    """
    Django WSGI middleware that attaches a UUID trace ID to each request,
    sets the X-Trace-Id response header, and fires lifecycle events.

    Also compatible with ASGI when used with Django's async request handling.
    Use ``ninja_boost.async_support.AsyncTracingMiddleware`` for pure ASGI
    stacks where you need native async middleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        trace_id = uuid.uuid4().hex
        request.trace_id = trace_id
        start = time.perf_counter()

        logger.debug("%s %s [trace=%s]", request.method, request.path, trace_id)

        response = self.get_response(request)

        duration_ms = (time.perf_counter() - start) * 1000
        response["X-Trace-Id"] = trace_id

        # Emit after_response for any handlers registered directly on the event bus
        # (LifecycleMiddleware provides this more completely if installed)
        try:
            from ninja_boost.events import AFTER_RESPONSE, event_bus
            event_bus.emit(
                AFTER_RESPONSE,
                request=request,
                ctx={
                    "trace_id": trace_id,
                    "ip": request.META.get("REMOTE_ADDR"),
                    "user": getattr(request, "auth", None),
                },
                response=response,
                duration_ms=duration_ms,
            )
        except Exception:
            pass

        return response
