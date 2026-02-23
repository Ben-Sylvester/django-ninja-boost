"""
ninja_boost.dependencies
~~~~~~~~~~~~~~~~~~~~~~~~
Request context dependency injection.

``inject_context`` wraps any view function and injects a ``ctx`` dict as the
second positional argument (right after ``request``).

The context dict contains:
    ctx["user"]     → authenticated principal from request.auth
    ctx["ip"]       → client IP (honours X-Forwarded-For for proxied setups)
    ctx["trace_id"] → per-request UUID hex string set by TracingMiddleware
                      (None if middleware is not installed)

Usage in a router::

    @router.get("/me", response=UserOut)
    def me(request, ctx):
        user_id = ctx["user"]["id"]   # depends on what your AUTH returns
        return UserService.get(user_id)

Opt out on a specific route with ``inject=False``::

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
        ctx = {
            "user":     getattr(request, "auth", None),
            "ip":       _client_ip(request),
            "trace_id": getattr(request, "trace_id", None),
        }
        return func(request, ctx, *args, **kwargs)

    return wrapper


def _client_ip(request) -> str:
    """Return the real client IP, honouring X-Forwarded-For when present."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")
