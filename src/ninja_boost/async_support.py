"""
ninja_boost.async_support
~~~~~~~~~~~~~~~~~~~~~~~~~
Full async view support for Django Ninja Boost.

Django Ninja supports async views natively via ASGI. ninja_boost's decorators
(rate_limit, require, inject_context, auto_paginate) are all sync by default.
This module provides async-native equivalents that work correctly with
``async def`` view functions.

How it works
------------
All ninja_boost decorators detect async view functions automatically and
switch to their async implementation. You don't need to use this module
directly in most cases — just write ``async def`` views normally::

    @router.get("/items")
    async def list_items(request, ctx):
        items = await Item.objects.all().acount()  # Django 4.1+ async ORM
        return {"count": items}

Explicit async wrappers (for custom middleware / decorators)::

    from ninja_boost.async_support import async_inject_context, async_paginate

    @router.get("/items")
    @async_inject_context
    @async_paginate
    async def list_items(request, ctx):
        return await Item.objects.all()

ASGI setup
----------
Set DJANGO_SETTINGS_MODULE and use an ASGI server (uvicorn, daphne)::

    # asgi.py
    import os
    from django.core.asgi import get_asgi_application
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")
    application = get_asgi_application()

    # Run with:
    # uvicorn myproject.asgi:application --workers 4
"""

import asyncio
import logging
from collections.abc import Callable
from functools import wraps
from typing import Any

from ninja.errors import HttpError

logger = logging.getLogger("ninja_boost.async")


# ── Detection helper ──────────────────────────────────────────────────────

def is_async(func: Callable) -> bool:
    """Return True if *func* is an async function or coroutine function."""
    return asyncio.iscoroutinefunction(func)


def ensure_sync(func: Callable) -> Callable:
    """
    Wrap an async function so it can be called synchronously.

    - Outside an event loop: uses ``asyncio.run()``.
    - Inside a running event loop (e.g. called from sync code under ASGI):
      runs the coroutine in a brand-new thread with its own event loop,
      avoiding the "This event loop is already running" error.
    """
    if not is_async(func):
        return func

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            asyncio.get_running_loop()
            # There is a running loop — we cannot call run_until_complete or
            # asyncio.run() here.  Spin up a fresh thread with its own loop.
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(asyncio.run, func(*args, **kwargs))
                return fut.result()
        except RuntimeError:
            # No running event loop in this thread — safe to use asyncio.run().
            return asyncio.run(func(*args, **kwargs))

    return wrapper


def ensure_async(func: Callable) -> Callable:
    """
    Wrap a sync function so it can be awaited.
    Runs the sync function in a thread executor to avoid blocking the event loop.
    """
    if is_async(func):
        return func

    @wraps(func)
    async def wrapper(*args, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))

    return wrapper


# ── Async inject_context ──────────────────────────────────────────────────

def async_inject_context(func: Callable) -> Callable:
    """
    Async variant of inject_context.

    Injects ctx dict as the second argument into async view functions::

        @router.get("/me")
        @async_inject_context
        async def me(request, ctx):
            user = await User.objects.aget(id=ctx["user"]["id"])
            return UserOut.from_orm(user)
    """
    @wraps(func)
    async def wrapper(request, *args, **kwargs) -> Any:
        from ninja_boost.dependencies import _client_ip
        ctx = {
            "user":     getattr(request, "auth", None),
            "ip":       _client_ip(request),
            "trace_id": getattr(request, "trace_id", None),
        }
        # Enrich with services if registry has entries
        from ninja_boost.services import service_registry
        if len(service_registry) > 0:
            ctx["services"] = service_registry.build_context(request, ctx)
        return await func(request, ctx, *args, **kwargs)

    return wrapper


# ── Async paginate ────────────────────────────────────────────────────────

async def _async_count(qs) -> int:
    """Async QuerySet count — uses Django 4.1+ acount() if available."""
    if hasattr(qs, "acount"):
        return await qs.acount()
    # Fallback: run sync count in executor
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, qs.count)


async def _async_slice(qs, start: int, end: int) -> list:
    """Async QuerySet slice — uses Django 4.1+ async iteration."""
    sliced = qs[start:end]
    if hasattr(sliced, "__aiter__"):
        return [item async for item in sliced]
    # Fallback: sync slice in executor
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, list, sliced)


def async_paginate(func: Callable) -> Callable:
    """
    Async variant of auto_paginate.

    Uses Django 4.1+ async ORM methods (acount, async iteration).
    Falls back to thread executor for older Django versions.
    """
    from ninja_boost.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, _is_queryset, _safe_int

    @wraps(func)
    async def wrapper(request, *args, **kwargs) -> Any:
        result = await func(request, *args, **kwargs)

        if result is None or isinstance(result, dict):
            return result

        page  = _safe_int(request.GET.get("page"), default=1, minimum=1)
        size  = _safe_int(request.GET.get("size"), default=DEFAULT_PAGE_SIZE,
                          minimum=1, maximum=MAX_PAGE_SIZE)
        start = (page - 1) * size
        end   = start + size

        if _is_queryset(result):
            total = await _async_count(result)
            items = await _async_slice(result, start, end)
        else:
            total = len(result)
            items = list(result[start:end])

        return {
            "items": items,
            "page":  page,
            "size":  size,
            "total": total,
            "pages": max(1, (total + size - 1) // size),
        }

    return wrapper


# ── Async rate limit ──────────────────────────────────────────────────────

def async_rate_limit(
    rate: str,
    key: str | Callable | None = None,
    error_message: str = "Rate limit exceeded. Please slow down.",
):
    """
    Async-compatible variant of the rate_limit decorator.

    Example::

        @router.get("/stream")
        @async_rate_limit("5/minute", key="user")
        async def stream(request, ctx): ...
    """
    from ninja_boost.events import ON_RATE_LIMIT_EXCEEDED, event_bus
    from ninja_boost.rate_limiting import _get_backend, _parse_rate, _resolve_key

    limit, window = _parse_rate(rate)

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(request, ctx: dict, *args, **kwargs) -> Any:
            resolved_key = _resolve_key(key, request, ctx)
            bucket_key   = f"{func.__module__}.{func.__qualname__}:{resolved_key}"

            backend = _get_backend()
            # Run the potentially sync backend in executor
            loop = asyncio.get_running_loop()
            allowed, remaining, retry_after = await loop.run_in_executor(
                None, backend.is_allowed, bucket_key, limit, window
            )

            if not allowed:
                event_bus.emit(
                    ON_RATE_LIMIT_EXCEEDED,
                    request=request, ctx=ctx, key=resolved_key, rate=rate,
                )
                raise HttpError(429, error_message)

            return await func(request, ctx, *args, **kwargs)

        wrapper._rate_limit = rate
        return wrapper
    return decorator


# ── Async permission check ────────────────────────────────────────────────

def async_require(*permissions, message: str = "Permission denied.", status: int = 403):
    """
    Async-compatible variant of require().

    Supports both sync and async permission objects::

        @router.get("/admin")
        @async_require(IsStaff)
        async def admin_view(request, ctx): ...
    """
    from ninja_boost.events import ON_PERMISSION_DENIED, event_bus

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(request, ctx: dict, *args, **kwargs) -> Any:
            for perm in permissions:
                try:
                    if is_async(perm.__call__):
                        allowed = await perm(request, ctx)
                    else:
                        loop = asyncio.get_running_loop()
                        allowed = await loop.run_in_executor(None, perm, request, ctx)
                except HttpError:
                    raise
                except Exception:
                    logger.exception("Async permission %r raised", perm)
                    allowed = False

                if not allowed:
                    event_bus.emit(ON_PERMISSION_DENIED, request=request, ctx=ctx,
                                   permission=repr(perm))
                    raise HttpError(status, message)

            return await func(request, ctx, *args, **kwargs)

        wrapper._permissions = list(permissions)
        return wrapper
    return decorator


# ── Auto-detect and dispatch ──────────────────────────────────────────────

def auto_wrap(
    sync_decorator: Callable,
    async_decorator: Callable,
) -> Callable:
    """
    Return a decorator that applies *sync_decorator* to sync functions
    and *async_decorator* to async functions.

    Used internally by AutoRouter to be decorator-agnostic::

        wrapped = auto_wrap(inject_context, async_inject_context)(view_func)
    """
    def dispatcher(func: Callable) -> Callable:
        if is_async(func):
            return async_decorator(func)
        return sync_decorator(func)
    return dispatcher


# ── Async lifecycle middleware ────────────────────────────────────────────

class AsyncTracingMiddleware:
    """
    Async-compatible version of TracingMiddleware for ASGI deployments.

    Supports both sync and async Django views seamlessly::

        MIDDLEWARE = [
            ...
            "ninja_boost.async_support.AsyncTracingMiddleware",
        ]
    """

    async_capable  = True
    sync_capable   = True

    def __init__(self, get_response):
        import uuid
        self._uuid = uuid
        self.get_response = get_response
        self._async_mode  = asyncio.iscoroutinefunction(get_response)

    def __call__(self, request):
        if self._async_mode:
            return self.__acall__(request)
        return self._sync_call(request)

    def _sync_call(self, request):
        import logging as _log
        import uuid
        _logger = _log.getLogger("ninja_boost.tracing")
        trace_id = uuid.uuid4().hex
        request.trace_id = trace_id
        _logger.debug("%s %s [trace=%s]", request.method, request.path, trace_id)
        response = self.get_response(request)
        response["X-Trace-Id"] = trace_id
        return response

    async def __acall__(self, request):
        import uuid
        trace_id = uuid.uuid4().hex
        request.trace_id = trace_id
        logger.debug("%s %s [trace=%s]", request.method, request.path, trace_id)
        response = await self.get_response(request)
        response["X-Trace-Id"] = trace_id
        return response
