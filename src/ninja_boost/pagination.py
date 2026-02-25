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

import base64
import json
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


# ── Cursor-based pagination ────────────────────────────────────────────────


def _encode_cursor(data: dict) -> str:
    """Encode cursor dict to a URL-safe base64 string."""
    return base64.urlsafe_b64encode(
        json.dumps(data, separators=(",", ":")).encode()
    ).decode().rstrip("=")


def _decode_cursor(token: str) -> dict | None:
    """Decode a cursor token back to dict, return None if invalid."""
    try:
        padding = 4 - len(token) % 4
        token += "=" * (padding % 4)
        return json.loads(base64.urlsafe_b64decode(token).decode())
    except Exception:
        return None


def cursor_paginate(field: str = "id", order: str = "asc"):
    """
    Cursor-based pagination decorator — O(1) regardless of dataset size.

    Unlike offset pagination (which slows as OFFSET grows), cursor pagination
    uses a keyset filter (``id > last_seen_id``) that stays fast on billion-row
    tables because it leverages the index on *field*.

    Use this instead of ``auto_paginate`` when:
      - Your table has > 100k rows
      - You need real-time feeds where rows can be inserted between pages
      - You want to avoid COUNT(*) queries

    Parameters
    ----------
    field:
        The field to paginate on. Must be unique and indexed. Default: ``"id"``.
    order:
        ``"asc"`` (newest last) or ``"desc"`` (newest first). Default: ``"asc"``.

    Query parameters
    ----------------
        ?cursor   opaque cursor string (absent on first page)
        ?size     items per page (default: 20, max: 200)

    Response shape
    --------------
    ::

        {
            "items":       [...],
            "next_cursor": "eyJpZCI6IDQyfQ",   # null on last page
            "prev_cursor": "eyJpZCI6IDIxfQ",   # null on first page
            "size":        20,
            "has_next":    true,
            "has_prev":    true
        }

    Example::

        @router.get("/events")
        @cursor_paginate(field="created_at", order="desc")
        def list_events(request, ctx):
            return Event.objects.order_by("-created_at")

        # First page:  GET /events?size=20
        # Second page: GET /events?cursor=<next_cursor from first page>
    """
    def decorator(func):
        import asyncio as _asyncio

        if _asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(request, *args, **kwargs) -> Any:
                from ninja_boost.async_support import _async_slice
                result = await func(request, *args, **kwargs)

                if result is None or isinstance(result, dict):
                    return result

                size = _safe_int(request.GET.get("size"), default=DEFAULT_PAGE_SIZE,
                                 minimum=1, maximum=MAX_PAGE_SIZE)
                cursor_token = request.GET.get("cursor")
                cursor_data  = _decode_cursor(cursor_token) if cursor_token else None

                if _is_queryset(result):
                    qs = result
                    if cursor_data:
                        cursor_val = cursor_data.get("v")
                        if order == "asc":
                            qs = qs.filter(**{f"{field}__gt": cursor_val})
                        else:
                            qs = qs.filter(**{f"{field}__lt": cursor_val})

                    items = await _async_slice(qs, 0, size + 1)
                    has_next = len(items) > size
                    if has_next:
                        items = items[:size]

                    has_prev = bool(cursor_data)
                    next_cursor = (
                        _encode_cursor({"v": getattr(items[-1], field)})
                        if has_next and items else None
                    )
                    prev_cursor = (
                        _encode_cursor({"v": getattr(items[0], field), "dir": "prev"})
                        if has_prev and items else None
                    )
                else:
                    start = cursor_data.get("i", 0) if cursor_data else 0
                    all_items = list(result)
                    chunk = all_items[start:start + size + 1]
                    has_next = len(chunk) > size
                    if has_next:
                        chunk = chunk[:size]
                    items = chunk
                    has_prev = start > 0
                    next_cursor = _encode_cursor({"i": start + size}) if has_next else None
                    prev_cursor = _encode_cursor({"i": max(0, start - size)}) if has_prev else None

                return {
                    "items":       items,
                    "next_cursor": next_cursor,
                    "prev_cursor": prev_cursor,
                    "size":        size,
                    "has_next":    has_next,
                    "has_prev":    has_prev,
                }

            async_wrapper._cursor_paginated = True
            async_wrapper._cursor_field     = field
            async_wrapper._cursor_order     = order
            return async_wrapper

        @wraps(func)
        def wrapper(request, *args, **kwargs) -> Any:
            result = func(request, *args, **kwargs)

            if result is None or isinstance(result, dict):
                return result

            size = _safe_int(request.GET.get("size"), default=DEFAULT_PAGE_SIZE,
                             minimum=1, maximum=MAX_PAGE_SIZE)
            cursor_token = request.GET.get("cursor")
            cursor_data  = _decode_cursor(cursor_token) if cursor_token else None

            if _is_queryset(result):
                # Apply cursor filter
                qs = result
                if cursor_data:
                    cursor_val = cursor_data.get("v")
                    if order == "asc":
                        qs = qs.filter(**{f"{field}__gt": cursor_val})
                    else:
                        qs = qs.filter(**{f"{field}__lt": cursor_val})

                # Fetch one extra to detect has_next
                items = list(qs[:size + 1])
                has_next = len(items) > size
                if has_next:
                    items = items[:size]

                has_prev = bool(cursor_data)
                next_cursor = (
                    _encode_cursor({"v": getattr(items[-1], field)})
                    if has_next and items else None
                )
                prev_cursor = (
                    _encode_cursor({"v": getattr(items[0], field), "dir": "prev"})
                    if has_prev and items else None
                )

            else:
                # List fallback: simple slice with cursor as index
                start = cursor_data.get("i", 0) if cursor_data else 0
                chunk = list(result)[start:start + size + 1]
                has_next = len(chunk) > size
                if has_next:
                    chunk = chunk[:size]
                items = chunk
                has_prev = start > 0
                next_cursor = _encode_cursor({"i": start + size}) if has_next else None
                prev_cursor = _encode_cursor({"i": max(0, start - size)}) if has_prev else None

            return {
                "items":       items,
                "next_cursor": next_cursor,
                "prev_cursor": prev_cursor,
                "size":        size,
                "has_next":    has_next,
                "has_prev":    has_prev,
            }

        wrapper._cursor_paginated = True
        wrapper._cursor_field     = field
        wrapper._cursor_order     = order
        return wrapper
    return decorator
