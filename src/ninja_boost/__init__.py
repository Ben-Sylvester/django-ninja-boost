"""
ninja_boost — Zero-boilerplate automation layer for Django Ninja.

Closes the ergonomic gap with FastAPI by auto-wiring the cross-cutting
concerns every production API needs: auth, response envelopes, pagination,
request context injection, and distributed tracing.

    pip install django-ninja django-ninja-boost

Basic usage::

    from ninja_boost import AutoAPI, AutoRouter

    api = AutoAPI()
    router = AutoRouter(tags=["Items"])

    @router.get("/", response=list[ItemOut])
    def list_items(request, ctx):
        return ItemService.list()   # QuerySet paginated automatically

"""

from ninja_boost.api import AutoAPI
from ninja_boost.router import AutoRouter
from ninja_boost.dependencies import inject_context
from ninja_boost.exceptions import register_exception_handlers
from ninja_boost.middleware import TracingMiddleware
from ninja_boost.pagination import auto_paginate
from ninja_boost.responses import wrap_response

__version__ = "0.1.0"

__all__ = [
    "AutoAPI",
    "AutoRouter",
    "inject_context",
    "register_exception_handlers",
    "TracingMiddleware",
    "auto_paginate",
    "wrap_response",
]
