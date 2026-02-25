"""
ninja_boost.idempotency
~~~~~~~~~~~~~~~~~~~~~~~~
Idempotency key support — safely retry POST/PATCH requests without
duplicating side effects.

An idempotency key is a client-supplied UUID that identifies a unique
intent. If the same key is submitted twice (e.g. after a network timeout),
the second request returns the stored result of the first — without
executing the view again.

This is essential for:
  - Payment APIs — never charge a card twice on retry
  - Order creation — never create a duplicate order
  - Email/SMS dispatch — never send the same message twice
  - Any mutation with real-world side effects

How it works
------------
1. Client sends ``X-Idempotency-Key: <uuid>`` on a POST/PATCH request
2. If the key has been seen before, the cached response is returned immediately
3. If the key is new, the view runs and its result is stored under that key
4. A replay is detectable via the ``X-Idempotency-Replay: true`` response header

Usage::

    from ninja_boost.idempotency import idempotent

    @router.post("/payments")
    @idempotent(ttl="24h")             # store result for 24 hours
    def charge_card(request, ctx, payload: ChargePayload):
        return PaymentService.charge(payload)

    # Client:
    # POST /api/payments
    # X-Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000
    # {"amount": 4999, "card_token": "..."}
    #
    # Retry (same key, network timed out):
    # POST /api/payments
    # X-Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000
    # → Returns cached result. Payment NOT charged again.

Key scope
---------
By default, idempotency keys are scoped per user: user A and user B can
use the same key string without conflict. Set ``scope="global"`` to make
keys global across all users::

    @idempotent(ttl="1h", scope="global")
    def create_job(request, ctx, payload): ...

Concurrent request protection
------------------------------
If two requests with the same key arrive simultaneously (race condition),
only one will execute. The other receives HTTP 409 Conflict and should
retry after a short delay::

    HTTP 409 Conflict
    {"ok": false, "error": "A request with this idempotency key is in progress.", "code": 409}

Configuration::

    NINJA_BOOST = {
        "IDEMPOTENCY": {
            "CACHE_ALIAS": "default",     # Django cache alias
            "PREFIX":      "boost:idem",  # key prefix
            "DEFAULT_TTL": 86400,         # 24 hours
            "HEADER":      "X-Idempotency-Key",
            "LOCK_TTL":    30,            # seconds to hold lock during execution
        }
    }
"""

import hashlib
import json
import logging
import time
from functools import wraps
from typing import Any, Callable

from ninja.errors import HttpError

logger = logging.getLogger("ninja_boost.idempotency")

# ── Sentinel values stored in cache ──────────────────────────────────────
_LOCK_SENTINEL = "__LOCK__"


# ── Settings helpers ─────────────────────────────────────────────────────

def _settings() -> dict:
    from django.conf import settings
    cfg = getattr(settings, "NINJA_BOOST", {})
    return cfg.get("IDEMPOTENCY", {})


def _cache():
    from django.core.cache import caches
    alias = _settings().get("CACHE_ALIAS", "default")
    return caches[alias]


def _prefix() -> str:
    return _settings().get("PREFIX", "boost:idem")


def _header_name() -> str:
    return _settings().get("HEADER", "X-Idempotency-Key")


def _default_ttl() -> int:
    return int(_settings().get("DEFAULT_TTL", 86400))


def _lock_ttl() -> int:
    return int(_settings().get("LOCK_TTL", 30))


# ── TTL parser (reuse from caching module pattern) ────────────────────────

_TTL_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def _parse_ttl(ttl: int | str) -> int:
    if isinstance(ttl, int):
        return ttl
    s = str(ttl).strip().lower()
    for suffix, factor in _TTL_UNITS.items():
        if s.endswith(suffix):
            try:
                return int(float(s[:-1]) * factor)
            except ValueError:
                pass
    return int(s)


# ── Key building ─────────────────────────────────────────────────────────

def _build_cache_key(idempotency_key: str, user_id: Any, scope: str, func_name: str) -> str:
    """Build a namespaced, bounded cache key."""
    if scope == "global":
        scope_part = "global"
    else:
        scope_part = f"user:{user_id or 'anon'}"

    raw = f"{func_name}:{scope_part}:{idempotency_key}"
    h = hashlib.sha256(raw.encode(), usedforsecurity=False).hexdigest()[:32]
    return f"{_prefix()}:{h}"


def _extract_user_id(ctx: dict) -> Any:
    user = ctx.get("user")
    if user is None:
        return None
    if isinstance(user, dict):
        return user.get("id") or user.get("user_id")
    return getattr(user, "id", None)


# ── Decorator ─────────────────────────────────────────────────────────────

def idempotent(
    ttl: int | str | None = None,
    scope: str = "user",            # "user" or "global"
    methods: list[str] | None = None,
    header: str | None = None,
):
    """
    Decorator: make a view idempotent using ``X-Idempotency-Key``.

    Parameters
    ----------
    ttl:
        How long to cache the response. Int seconds or string like ``"24h"``.
        Defaults to ``NINJA_BOOST["IDEMPOTENCY"]["DEFAULT_TTL"]`` (86400s / 24h).
    scope:
        ``"user"`` (default) — key is unique per user.
        ``"global"`` — key is unique across all users.
    methods:
        HTTP methods this decorator applies to. Default: ``["POST", "PATCH"]``.
        GET/DELETE are idempotent by nature and don't need this.
    header:
        Override the header name. Default: ``"X-Idempotency-Key"``.

    Behaviour
    ---------
    - If no idempotency key header is present, the view runs normally.
    - If the key has a stored result, that result is returned (no view execution).
    - If the key is locked (concurrent request), HTTP 409 is raised.
    - If the key is new, the view runs and the result is stored.

    Response headers on a replay:
        ``X-Idempotency-Replay: true``
        ``X-Idempotency-Key: <the-key>``
    """
    _methods = [m.upper() for m in (methods or ["POST", "PATCH"])]

    def decorator(func: Callable) -> Callable:
        import asyncio as _asyncio
        func_name = f"{func.__module__}.{func.__qualname__}"

        if _asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(request, ctx: dict, *args, **kwargs) -> Any:
                if request.method.upper() not in _methods:
                    return await func(request, ctx, *args, **kwargs)

                header_name = (header or _header_name()).upper().replace("-", "_")
                ikey = request.META.get(f"HTTP_{header_name}")
                if not ikey:
                    return await func(request, ctx, *args, **kwargs)

                user_id      = _extract_user_id(ctx)
                cache_key    = _build_cache_key(ikey, user_id, scope, func_name)
                lock_key     = f"{cache_key}:lock"
                resolved_ttl = _parse_ttl(ttl) if ttl is not None else _default_ttl()
                cache        = _cache()

                try:
                    stored = cache.get(cache_key)
                    if stored is not None and stored != _LOCK_SENTINEL:
                        logger.debug("Idempotency replay: key=%s func=%s", ikey[:8], func_name)
                        request._idempotency_replay = True
                        request._idempotency_key    = ikey
                        return json.loads(stored)
                except Exception:
                    logger.debug("Idempotency cache GET failed", exc_info=True)

                try:
                    lock_acquired = cache.add(lock_key, _LOCK_SENTINEL, timeout=_lock_ttl())
                    if not lock_acquired:
                        raise HttpError(
                            409,
                            "A request with this idempotency key is already in progress. "
                            "Please retry after a moment.",
                        )
                except HttpError:
                    raise
                except Exception:
                    logger.debug("Idempotency lock check failed — proceeding without lock", exc_info=True)
                    lock_acquired = False

                try:
                    result = await func(request, ctx, *args, **kwargs)
                except Exception:
                    raise
                finally:
                    if lock_acquired:
                        try:
                            cache.delete(lock_key)
                        except Exception:
                            pass

                try:
                    cache.set(cache_key, json.dumps(result, default=str), timeout=resolved_ttl)
                    request._idempotency_key = ikey
                except Exception:
                    logger.debug("Idempotency cache SET failed", exc_info=True)

                return result

            async_wrapper._idempotent     = True
            async_wrapper._idempotent_ttl = ttl
            return async_wrapper

        @wraps(func)
        def wrapper(request, ctx: dict, *args, **kwargs) -> Any:
            # Only apply to configured HTTP methods
            if request.method.upper() not in _methods:
                return func(request, ctx, *args, **kwargs)

            # Extract idempotency key from request header
            header_name = (header or _header_name()).upper().replace("-", "_")
            ikey = request.META.get(f"HTTP_{header_name}")

            if not ikey:
                # No idempotency key — run normally
                return func(request, ctx, *args, **kwargs)

            user_id = _extract_user_id(ctx)
            cache_key  = _build_cache_key(ikey, user_id, scope, func_name)
            lock_key   = f"{cache_key}:lock"
            resolved_ttl = _parse_ttl(ttl) if ttl is not None else _default_ttl()

            cache = _cache()

            # Check for existing result
            try:
                stored = cache.get(cache_key)
                if stored is not None and stored != _LOCK_SENTINEL:
                    logger.debug("Idempotency replay: key=%s func=%s", ikey[:8], func_name)
                    result = json.loads(stored)
                    # Mark request so middleware can add replay header
                    request._idempotency_replay = True
                    request._idempotency_key    = ikey
                    return result
            except Exception:
                logger.debug("Idempotency cache GET failed", exc_info=True)

            # Check for concurrent execution lock
            try:
                lock_acquired = cache.add(lock_key, _LOCK_SENTINEL, timeout=_lock_ttl())
                if not lock_acquired:
                    raise HttpError(
                        409,
                        "A request with this idempotency key is already in progress. "
                        "Please retry after a moment.",
                    )
            except HttpError:
                raise
            except Exception:
                logger.debug("Idempotency lock check failed — proceeding without lock", exc_info=True)
                lock_acquired = False

            try:
                result = func(request, ctx, *args, **kwargs)
            except Exception:
                # Don't cache failures — client should fix and retry
                raise
            finally:
                if lock_acquired:
                    try:
                        cache.delete(lock_key)
                    except Exception:
                        pass

            # Store the result
            try:
                cache.set(cache_key, json.dumps(result, default=str), timeout=resolved_ttl)
                request._idempotency_key = ikey
            except Exception:
                logger.debug("Idempotency cache SET failed", exc_info=True)

            return result

        wrapper._idempotent    = True
        wrapper._idempotent_ttl = ttl
        return wrapper

    return decorator


# ── Middleware: inject replay headers ─────────────────────────────────────

class IdempotencyMiddleware:
    """
    Middleware that adds idempotency response headers.

    Add after TracingMiddleware::

        MIDDLEWARE = [
            ...
            "ninja_boost.middleware.TracingMiddleware",
            "ninja_boost.idempotency.IdempotencyMiddleware",
        ]

    Adds to replayed responses:
        X-Idempotency-Replay: true
        X-Idempotency-Key: <the-key>
    """

    async_capable = True
    sync_capable  = True

    def __init__(self, get_response):
        import asyncio as _asyncio
        self.get_response = get_response
        self._is_async    = _asyncio.iscoroutinefunction(get_response)

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
        if getattr(request, "_idempotency_replay", False):
            response["X-Idempotency-Replay"] = "true"
        key = getattr(request, "_idempotency_key", None)
        if key:
            response["X-Idempotency-Key"] = key
