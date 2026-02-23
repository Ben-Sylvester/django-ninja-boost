"""
ninja_boost.middleware
~~~~~~~~~~~~~~~~~~~~~~
TracingMiddleware — stamps every request with a UUID trace ID.

The ID is available as ``request.trace_id`` inside any view and is injected
into the DI context dict (``ctx["trace_id"]``) when using AutoRouter.

It is also forwarded as an ``X-Trace-Id`` response header so clients and APM
tools (Datadog, Sentry, OpenTelemetry) can correlate logs across services.

Setup
-----
Add to ``MIDDLEWARE`` in settings.py::

    MIDDLEWARE = [
        ...
        "ninja_boost.middleware.TracingMiddleware",   # ← add here
    ]

Then in any view (when using AutoRouter)::

    @router.get("/orders/{id}")
    def get_order(request, ctx, id: int):
        logger.info("trace=%s", ctx["trace_id"])
        return OrderService.get(id)
"""

import uuid
import logging

logger = logging.getLogger("ninja_boost.tracing")


class TracingMiddleware:
    """Django WSGI middleware that attaches a UUID trace ID to each request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        trace_id = uuid.uuid4().hex
        request.trace_id = trace_id

        logger.debug("%s %s [trace=%s]", request.method, request.path, trace_id)

        response = self.get_response(request)
        response["X-Trace-Id"] = trace_id
        return response
