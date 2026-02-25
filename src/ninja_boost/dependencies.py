"""
ninja_boost.dependencies
~~~~~~~~~~~~~~~~~~~~~~~~
Request context dependency injection.

``inject_context`` wraps any view function and injects a ``ctx`` dict as the
second positional argument (right after ``request``).

Context dict contents
----------------------
    ctx["user"]       → authenticated principal from request.auth
    ctx["ip"]         → client IP (honours X-Forwarded-For)
    ctx["trace_id"]   → per-request UUID hex (set by TracingMiddleware)
    ctx["services"]   → {name: service_instance} from the service registry
                        (only populated if services are registered)

Opt out on a specific route::

    @router.get("/ping", inject=False, auth=None, paginate=False)
    def ping(request):
        return {"pong": True}
"""

from functools import wraps
from typing import Any


def inject_context(func):
    """Decorator: inject ``ctx`` dict as the second argument of the view."""

    @wraps(func)
    def wrapper(request, *args, **kwargs) -> Any:
        ctx: dict[str, Any] = {
            "user":     getattr(request, "auth", None),
            "ip":       _client_ip(request),
            "trace_id": getattr(request, "trace_id", None),
        }

        # Enrich with service registry if any services are registered
        try:
            from ninja_boost.services import service_registry
            if len(service_registry) > 0:
                ctx["services"] = service_registry.build_context(request, ctx)
        except Exception:
            pass

        # Fire before_request event
        try:
            from ninja_boost.events import BEFORE_REQUEST, event_bus
            event_bus.emit(BEFORE_REQUEST, request=request, ctx=ctx)
        except Exception:
            pass

        return func(request, ctx, *args, **kwargs)

    return wrapper


def _client_ip(request) -> str:
    """Return the real client IP, honouring X-Forwarded-For when present."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")
