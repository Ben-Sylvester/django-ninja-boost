"""
ninja_boost.router
~~~~~~~~~~~~~~~~~~
AutoRouter — a Router subclass that auto-applies auth, DI, pagination,
rate limiting, permissions, async detection, and lifecycle events to every
registered operation.

Drop-in replacement for Router::

    from ninja_boost import AutoRouter
    router = AutoRouter(tags=["Users"])

Per-operation opt-outs::

    @router.get("/health", auth=None, inject=False, paginate=False)
    def health(request):
        return {"status": "ok"}

    @router.post("/", response=UserOut, paginate=False)
    def create_user(request, ctx, payload: UserCreate):
        return UserService.create(payload)

Rate limiting per route::

    from ninja_boost.rate_limiting import rate_limit

    @router.get("/search")
    @rate_limit("30/minute")
    def search(request, ctx, q: str): ...

Declarative permissions::

    from ninja_boost.permissions import require, IsAuthenticated, IsStaff

    @router.delete("/{id}")
    @require(IsStaff)
    def delete_item(request, ctx, id: int): ...

Async views are automatically detected::

    @router.get("/items")
    async def list_items(request, ctx):
        return await Item.objects.all()

Decorator application order (innermost first, outermost called first):
    auto_paginate( inject_context( view_func ) )
"""

import asyncio
import logging
from typing import Any

from ninja import Router
from ninja_boost.conf import boost_settings

logger = logging.getLogger("ninja_boost.router")


class AutoRouter(Router):
    """
    Router that auto-applies DI injection, pagination, auth, rate limiting,
    and lifecycle events per-operation.

    Extra kwargs consumed before passing to super():
        inject   (bool, default True)  — apply inject_context
        paginate (bool, default True)  — apply auto_paginate
    """

    def add_api_operation(self, path: str, methods, view_func, **kwargs):
        is_async_view = asyncio.iscoroutinefunction(view_func)

        # ── Auth ──────────────────────────────────────────────────────────
        if "auth" not in kwargs:
            kwargs["auth"] = boost_settings.AUTH()

        # ── Global rate limit ─────────────────────────────────────────────
        # Applied BEFORE inject_context so that rate_limit's wrapper receives
        # ctx as its second argument (injected by the outer inject_context call).
        # Call chain: paginate → inject_context → rate_limit → view   ✓
        try:
            from ninja_boost.rate_limiting import _get_global_rate, apply_global_rate_limit
            global_rate = _get_global_rate()
            if global_rate:
                if is_async_view:
                    from ninja_boost.async_support import async_rate_limit
                    view_func = async_rate_limit(global_rate)(view_func)
                else:
                    view_func = apply_global_rate_limit(view_func, global_rate)
        except Exception:
            logger.debug("Global rate limit wiring skipped", exc_info=True)

        # ── Dependency injection ──────────────────────────────────────────
        if kwargs.pop("inject", True):
            if is_async_view:
                from ninja_boost.async_support import async_inject_context
                view_func = async_inject_context(view_func)
            else:
                view_func = boost_settings.DI(view_func)

        # ── Pagination ────────────────────────────────────────────────────
        if kwargs.pop("paginate", True):
            if is_async_view:
                from ninja_boost.async_support import async_paginate
                view_func = async_paginate(view_func)
            else:
                view_func = boost_settings.PAGINATION(view_func)

        return super().add_api_operation(path, methods, view_func, **kwargs)
