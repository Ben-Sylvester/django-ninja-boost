"""
ninja_boost.exceptions
~~~~~~~~~~~~~~~~~~~~~~
Standard exception handler registration.

Call ``register_exception_handlers(api)`` once after creating your AutoAPI
instance to get consistent error envelopes across all endpoints::

    api = AutoAPI()
    register_exception_handlers(api)

Error envelope shape::

    {"ok": False, "error": "<human readable message>", "code": <http status>}

The ``"ok"`` key prevents AutoAPI.create_response from double-wrapping errors.
"""

from ninja.errors import HttpError


def register_exception_handlers(api) -> None:
    """Register standard HTTP and generic exception handlers on *api*."""

    @api.exception_handler(HttpError)
    def handle_http(request, exc: HttpError):
        return api.create_response(
            request,
            {"ok": False, "error": str(exc.message), "code": exc.status_code},
            status=exc.status_code,
        )

    @api.exception_handler(Exception)
    def handle_generic(request, exc: Exception):
        return api.create_response(
            request,
            {"ok": False, "error": "Internal server error.", "code": 500},
            status=500,
        )
