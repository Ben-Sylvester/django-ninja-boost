"""
ninja_boost.pagination
~~~~~~~~~~~~~~~~~~~~~~
Transparent, automatic pagination for list and QuerySet responses.

``auto_paginate`` wraps a view function. If the view returns a list or Django
QuerySet, it slices it according to ``?page=`` and ``?size=`` query params and
returns a structured pagination envelope.

Performance note
----------------
For Django QuerySets this decorator uses ``.count()`` (one ``COUNT(*)`` query)
followed by a LIMIT/OFFSET slice — two efficient SQL queries. It never calls
``len(queryset)`` which would load the entire table into memory.

Query parameters
----------------
    ?page   int, 1-based page number  (default: 1)
    ?size   int, items per page       (default: 20, max: 200)

Response shape
--------------
::

    {
        "items": [...],
        "page":  1,
        "size":  20,
        "total": 142,
        "pages": 8
    }

The envelope above becomes the ``"data"`` value inside AutoAPI's outer wrapper::

    {"ok": True, "data": {"items": [...], "page": 1, ...}}

Opt out per-route
-----------------
::

    @router.post("/", response=ItemOut, paginate=False)
    def create_item(request, ctx, payload: ItemCreate):
        return ItemService.create(payload)   # single object, skip pagination
"""

from functools import wraps
from typing import Any

MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 20


def auto_paginate(func):
    """Decorator: transparently paginate list / QuerySet return values."""

    @wraps(func)
    def wrapper(request, *args, **kwargs) -> Any:
        result = func(request, *args, **kwargs)

        # Pass through dict responses and None (single object, already structured)
        if result is None or isinstance(result, dict):
            return result

        page = _safe_int(request.GET.get("page"), default=1, minimum=1)
        size = _safe_int(request.GET.get("size"), default=DEFAULT_PAGE_SIZE,
                         minimum=1, maximum=MAX_PAGE_SIZE)

        start = (page - 1) * size
        end   = start + size

        if _is_queryset(result):
            total = result.count()          # COUNT(*) — no full table load
            items = list(result[start:end]) # LIMIT/OFFSET slice
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


# ── Helpers ────────────────────────────────────────────────────────────────

def _safe_int(value, *, default: int, minimum: int = 1,
              maximum: int = 2 ** 31) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, v))


def _is_queryset(obj) -> bool:
    """Detect Django QuerySets without importing the ORM (avoids circular deps)."""
    return hasattr(obj, "count") and hasattr(obj, "filter") and hasattr(obj, "values")
