"""
ninja_boost.exceptions
~~~~~~~~~~~~~~~~~~~~~~
Standard exception handler registration with event emission.

Call ``register_exception_handlers(api)`` once after creating your AutoAPI
instance::

    api = AutoAPI()
    register_exception_handlers(api)

Error envelope shape::

    {"ok": False, "error": "<human readable>", "code": <http status>}

The ``"ok"`` key prevents AutoAPI.create_response from double-wrapping.
"""

import logging

from ninja.errors import HttpError

logger = logging.getLogger("ninja_boost.exceptions")


def register_exception_handlers(api) -> None:
    """Register standard HTTP and generic exception handlers on *api*."""

    @api.exception_handler(HttpError)
    def handle_http(request, exc: HttpError):
        logger.info(
            "HttpError %s: %s [trace=%s]",
            exc.status_code, exc.message,
            getattr(request, "trace_id", "-"),
        )
        return api.create_response(
            request,
            {"ok": False, "error": str(exc.message), "code": exc.status_code},
            status=exc.status_code,
        )

    @api.exception_handler(Exception)
    def handle_generic(request, exc: Exception):
        logger.exception(
            "Unhandled exception [trace=%s]",
            getattr(request, "trace_id", "-"),
        )
        # Fire on_error event for plugins / Sentry / alerting
        try:
            from ninja_boost.events import ON_ERROR, event_bus
            ctx = {
                "trace_id": getattr(request, "trace_id", None),
                "ip":       request.META.get("REMOTE_ADDR"),
                "user":     getattr(request, "auth", None),
            }
            event_bus.emit(ON_ERROR, request=request, ctx=ctx, exc=exc)
        except Exception:
            pass

        return api.create_response(
            request,
            {"ok": False, "error": "Internal server error.", "code": 500},
            status=500,
        )
