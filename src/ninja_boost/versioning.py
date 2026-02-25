"""
ninja_boost.versioning
~~~~~~~~~~~~~~~~~~~~~~~
API versioning utilities for URL-based and header-based versioning.

Strategy A — URL prefix versioning (recommended, most visible)::

    # urls.py
    from ninja_boost import AutoAPI
    from ninja_boost.versioning import versioned_api

    api_v1 = AutoAPI(title="My API", version="1.0")
    api_v2 = AutoAPI(title="My API", version="2.0")

    api_v1.add_router("/users", v1_users_router)
    api_v2.add_router("/users", v2_users_router)

    urlpatterns = [
        path("api/v1/", api_v1.urls),
        path("api/v2/", api_v2.urls),
    ]

Strategy B — Header versioning (X-API-Version)::

    from ninja_boost.versioning import version_router, require_version

    @router.get("/users")
    @require_version("2.0", header="X-API-Version")
    def list_users_v2(request, ctx): ...

Strategy C — ``VersionedRouter`` — auto-routes by version::

    from ninja_boost.versioning import VersionedRouter

    router = VersionedRouter(prefix="/users")

    @router.v1.get("/")
    def list_users_v1(request, ctx): ...

    @router.v2.get("/")
    def list_users_v2(request, ctx): ...

    # api.add_router("/users", router.for_version("v1"))
    # api.add_router("/users", router.for_version("v2"))

Deprecation warnings::

    from ninja_boost.versioning import deprecated

    @router.get("/old-endpoint")
    @deprecated(sunset="2026-12-31", replacement="/api/v2/new-endpoint")
    def old_endpoint(request, ctx): ...
    # Adds Deprecation and Sunset headers to the response
"""

import logging
from functools import wraps
from typing import Any, Callable

from ninja_boost.router import AutoRouter

logger = logging.getLogger("ninja_boost.versioning")


# ── Version extraction ────────────────────────────────────────────────────

def get_request_version(request, header: str = "X-API-Version") -> str | None:
    """Extract version string from a request header."""
    header_key = f"HTTP_{header.upper().replace('-', '_')}"
    return request.META.get(header_key)


# ── Decorator: require specific version ───────────────────────────────────

def require_version(
    version: str,
    header: str = "X-API-Version",
    error_message: str | None = None,
):
    """
    Decorator: only serve this endpoint if the request specifies *version*.

    Clients that send a different version (or no header) receive 400.
    Use in combination with URL versioning for header-based negotiation.
    """
    import asyncio as _asyncio
    from ninja.errors import HttpError

    def decorator(func: Callable) -> Callable:
        def _check(request) -> None:
            req_version = get_request_version(request, header)
            if req_version != version:
                msg = error_message or (
                    f"This endpoint requires {header}: {version}. "
                    f"You sent: {req_version or '(none)'}."
                )
                raise HttpError(400, msg)

        if _asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(request, *args, **kwargs) -> Any:
                _check(request)
                return await func(request, *args, **kwargs)
            async_wrapper._required_version = version
            return async_wrapper

        @wraps(func)
        def wrapper(request, *args, **kwargs) -> Any:
            _check(request)
            return func(request, *args, **kwargs)
        wrapper._required_version = version
        return wrapper
    return decorator


# ── Decorator: deprecation headers ────────────────────────────────────────

def deprecated(sunset: str | None = None, replacement: str | None = None):
    """
    Mark an endpoint as deprecated. Adds standard HTTP deprecation headers.

    Parameters
    ----------
    sunset:
        ISO 8601 date string when the endpoint will be removed (e.g. "2026-12-31").
        Adds a ``Sunset`` header to every response.
    replacement:
        URL of the replacement endpoint. Adds a ``Link`` header.

    RFC 8594 deprecation headers::
        Deprecation: true
        Sunset: Sat, 31 Dec 2026 00:00:00 GMT
        Link: <https://api.example.com/v2/users>; rel="successor-version"
    """
    def decorator(func: Callable) -> Callable:
        import asyncio as _asyncio

        def _tag(request) -> None:
            request._deprecation_sunset      = sunset
            request._deprecation_replacement = replacement

        if _asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(request, *args, **kwargs) -> Any:
                result = await func(request, *args, **kwargs)
                _tag(request)
                return result
            async_wrapper._deprecated   = True
            async_wrapper._sunset       = sunset
            async_wrapper._replacement  = replacement
            return async_wrapper

        @wraps(func)
        def wrapper(request, *args, **kwargs) -> Any:
            result = func(request, *args, **kwargs)
            _tag(request)
            return result

        wrapper._deprecated    = True
        wrapper._sunset        = sunset
        wrapper._replacement   = replacement
        return wrapper
    return decorator


class DeprecationMiddleware:
    """
    Middleware that attaches Deprecation/Sunset headers for deprecated routes.
    Add after TracingMiddleware::

        MIDDLEWARE = [
            ...
            "ninja_boost.middleware.TracingMiddleware",
            "ninja_boost.versioning.DeprecationMiddleware",
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
        response = self.get_response(request)
        self._set_headers(request, response)
        return response

    async def __acall__(self, request):
        response = await self.get_response(request)
        self._set_headers(request, response)
        return response

    @staticmethod
    def _set_headers(request, response) -> None:
        if getattr(request, "_deprecation_sunset", None) or getattr(request, "_deprecation_replacement", None):
            response["Deprecation"] = "true"
            if request._deprecation_sunset:
                response["Sunset"] = request._deprecation_sunset
            if request._deprecation_replacement:
                response["Link"] = f'<{request._deprecation_replacement}>; rel="successor-version"'


# ── VersionedRouter ───────────────────────────────────────────────────────

class VersionedRouter:
    """
    Convenience wrapper that creates one AutoRouter per API version.

    Provides ``router.v1``, ``router.v2``, ... attributes::

        from ninja_boost.versioning import VersionedRouter

        users = VersionedRouter()

        @users.v1.get("/")
        def list_users_v1(request, ctx): ...

        @users.v2.get("/")
        def list_users_v2(request, ctx): ...

        # In urls.py:
        api_v1.add_router("/users", users.v1)
        api_v2.add_router("/users", users.v2)
    """

    def __init__(self, **router_kwargs):
        self._kwargs   = router_kwargs
        self._routers: dict[str, AutoRouter] = {}

    def __getattr__(self, name: str) -> AutoRouter:
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in self._routers:
            self._routers[name] = AutoRouter(**self._kwargs)
        return self._routers[name]

    def for_version(self, version: str) -> AutoRouter:
        """Return the router for *version* (e.g. ``"v1"``)."""
        return getattr(self, version)

    @property
    def versions(self) -> list[str]:
        return list(self._routers.keys())


# ── Multi-API builder ─────────────────────────────────────────────────────

def versioned_api(
    versions: list[str],
    **api_kwargs,
) -> dict[str, Any]:
    """
    Create one AutoAPI instance per version string.

    Returns a dict ``{"v1": AutoAPI, "v2": AutoAPI, ...}``.

    Example::

        from ninja_boost.versioning import versioned_api

        apis = versioned_api(["v1", "v2"], title="Bookstore API")
        apis["v1"].add_router("/books", books_v1_router)
        apis["v2"].add_router("/books", books_v2_router)

        # In urls.py:
        urlpatterns = [
            path(f"api/{ver}/", api.urls)
            for ver, api in apis.items()
        ]
    """
    from ninja_boost.api import AutoAPI
    result = {}
    for version in versions:
        result[version] = AutoAPI(version=version, **api_kwargs)
    return result
