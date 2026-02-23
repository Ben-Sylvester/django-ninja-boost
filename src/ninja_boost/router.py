"""
ninja_boost.router
~~~~~~~~~~~~~~~~~~
AutoRouter — a Router subclass that auto-applies auth, DI, and pagination
to every registered operation.

How to integrate into an existing Django Ninja project
------------------------------------------------------
Same one-line swap as AutoAPI:

    # Before:
    from ninja import Router
    router = Router(tags=["Users"])

    # After:
    from ninja_boost import AutoRouter
    router = AutoRouter(tags=["Users"])

Your route functions stay exactly the same, except they now receive a ``ctx``
second argument containing the request context (see inject_context).

Per-operation opt-outs
----------------------
Use keyword flags when you need to skip a behaviour for a specific route:

    @router.get("/health", auth=None, inject=False, paginate=False)
    def health(request):
        return {"status": "ok"}

    @router.post("/", response=UserOut, paginate=False)
    def create_user(request, ctx, payload: UserCreate):
        # single object — no pagination needed
        return UserService.create(payload)

Decorator application order (innermost applied first, outermost called first):
    auto_paginate( inject_context( view_func ) )
"""

from ninja import Router
from ninja_boost.conf import boost_settings


class AutoRouter(Router):
    """
    Router that auto-applies DI context injection and pagination per-operation.

    Authentication is also wired automatically from ``settings.NINJA_BOOST["AUTH"]``
    unless ``auth=...`` is explicitly passed.

    Extra kwargs (consumed before passing to super):
        inject  (bool, default True)  — apply inject_context
        paginate (bool, default True) — apply auto_paginate
    """

    def add_api_operation(self, path: str, methods, view_func, **kwargs):
        # ── Auth ─────────────────────────────────────────────────────────────
        if "auth" not in kwargs:
            kwargs["auth"] = boost_settings.AUTH()

        # ── Dependency injection ──────────────────────────────────────────────
        if kwargs.pop("inject", True):
            view_func = boost_settings.DI(view_func)

        # ── Pagination ────────────────────────────────────────────────────────
        if kwargs.pop("paginate", True):
            view_func = boost_settings.PAGINATION(view_func)

        return super().add_api_operation(path, methods, view_func, **kwargs)
