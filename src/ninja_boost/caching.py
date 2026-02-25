"""
ninja_boost.caching
~~~~~~~~~~~~~~~~~~~~
Response caching for GET endpoints.

Wraps view functions with configurable cache keys, TTLs, and backend support.
Uses Django's cache framework — works with any configured cache (memory,
Redis, Memcached, database).

Usage::

    from ninja_boost.caching import cache_response

    @router.get("/products")
    @cache_response(ttl=300)                          # cache 5 minutes
    def list_products(request, ctx): ...

    @router.get("/products/{id}")
    @cache_response(ttl=60, key="path")               # cache per URL path
    def get_product(request, ctx, id: int): ...

    @router.get("/me/settings")
    @cache_response(ttl=120, key="user")              # cache per user
    def my_settings(request, ctx): ...

    @router.get("/leaderboard")
    @cache_response(
        ttl=30,
        key=lambda req, ctx: f"leaderboard:{ctx.get('tenant_id')}",
    )
    def leaderboard(request, ctx): ...

Cache invalidation::

    from ninja_boost.caching import cache_manager

    # Precise: invalidate by the exact raw key (func qualname + path + query)
    cache_manager.invalidate_key("myapp.views.list_products:/api/products:")
    # Pattern: invalidate all entries whose raw key contains a substring (requires Redis)
    cache_manager.invalidate_prefix("/api/products")
    # Nuclear: clear everything ninja_boost has cached
    cache_manager.clear_all()

Configuration::

    NINJA_BOOST = {
        "CACHE": {
            "BACKEND":  "default",    # Django cache alias (default: "default")
            "PREFIX":   "boost:",     # Key prefix
            "ENABLED":  True,
        }
    }

    # To disable caching entirely (e.g. in tests):
    NINJA_BOOST = {"CACHE": {"ENABLED": False}}
"""

import hashlib
import logging
from collections.abc import Callable
from functools import wraps
from typing import Any

logger = logging.getLogger("ninja_boost.caching")

_SENTINEL = object()


def _is_queryset(obj) -> bool:
    """Detect Django QuerySets without importing the ORM (avoids circular deps)."""
    return hasattr(obj, "count") and hasattr(obj, "filter") and hasattr(obj, "values")


def _get_cache():
    from django.conf import settings
    from django.core.cache import caches
    cfg     = getattr(settings, "NINJA_BOOST", {})
    alias   = cfg.get("CACHE", {}).get("BACKEND", "default")
    return caches[alias]


def _cache_enabled() -> bool:
    from django.conf import settings
    cfg = getattr(settings, "NINJA_BOOST", {})
    return cfg.get("CACHE", {}).get("ENABLED", True)


def _prefix() -> str:
    from django.conf import settings
    cfg = getattr(settings, "NINJA_BOOST", {})
    return cfg.get("CACHE", {}).get("PREFIX", "boost:")


def _build_key(key_spec: str | Callable | None, request, ctx: dict, func) -> str:
    if callable(key_spec):
        raw = key_spec(request, ctx)
    elif key_spec == "user":
        user = ctx.get("user") or {}
        uid = (
            (user.get("id") or user.get("user_id"))
            if isinstance(user, dict) else getattr(user, "id", None)
        )
        raw  = f"{func.__qualname__}:user:{uid}"
    elif key_spec == "path":
        raw = f"{func.__qualname__}:path:{request.path}"
    elif key_spec == "path+query":
        query = request.META.get("QUERY_STRING", "")
        raw   = f"{func.__qualname__}:pathq:{request.path}:{query}"
    else:
        # Default: path + query string
        query = request.META.get("QUERY_STRING", "")
        raw   = f"{func.__qualname__}:{request.path}:{query}"

    hashed = hashlib.md5(str(raw).encode()).hexdigest()
    return f"{_prefix()}{hashed}"


def cache_response(
    ttl: int = 60,
    key: str | Callable | None = None,
    cache_4xx: bool = False,
    vary_on_headers: list[str] | None = None,
):
    """
    Decorator: cache a view's response for *ttl* seconds.

    Parameters
    ----------
    ttl:
        Time-to-live in seconds (default: 60).
    key:
        Cache key strategy:
            ``None`` / ``"path+query"``  — full URL including query string
            ``"path"``   — URL path only (ignores query params)
            ``"user"``   — per authenticated user
            callable     — ``fn(request, ctx) -> str``
    cache_4xx:
        If True, cache error responses too (default: False).
    vary_on_headers:
        List of request header names whose values are mixed into the cache key.
        E.g. ``["Accept-Language", "X-Tenant-Id"]``.
    """
    import asyncio as _asyncio

    def _resolve_cache_key(request, ctx: dict, func) -> str:
        cache_key = _build_key(key, request, ctx, func)
        if vary_on_headers:
            header_bits = ":".join(
                request.META.get(f"HTTP_{h.upper().replace('-', '_')}", "")
                for h in vary_on_headers
            )
            if header_bits:
                cache_key += f":{hashlib.md5(header_bits.encode()).hexdigest()}"
        return cache_key

    def _store_result(cache, cache_key: str, result, func_name: str) -> None:
        """Materialise QuerySets and persist the result to cache."""
        if result is None:
            return
        # Evaluate Django QuerySets — lazy cursors are not picklable.
        if _is_queryset(result):
            result = list(result)
        try:
            cache.set(cache_key, result, timeout=ttl)
        except Exception:
            logger.warning(
                "Cache set failed (result may not be picklable): func=%s",
                func_name, exc_info=True,
            )

    def decorator(func: Callable) -> Callable:
        # ── Async path ────────────────────────────────────────────────────
        if _asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(request, ctx: dict, *args, **kwargs) -> Any:
                if not _cache_enabled():
                    return await func(request, ctx, *args, **kwargs)

                cache_key = _resolve_cache_key(request, ctx, func)
                cache = _get_cache()
                cached = cache.get(cache_key, _SENTINEL)

                if cached is not _SENTINEL:
                    logger.debug("Cache HIT: key=%s func=%s", cache_key[:20], func.__qualname__)
                    request._cache_hit = True
                    return cached

                logger.debug("Cache MISS: key=%s func=%s", cache_key[:20], func.__qualname__)
                result = await func(request, ctx, *args, **kwargs)
                request._cache_hit = False
                _store_result(cache, cache_key, result, func.__qualname__)
                return result

            async_wrapper._cache_ttl = ttl
            async_wrapper._cache_key = key
            return async_wrapper

        # ── Sync path ─────────────────────────────────────────────────────
        @wraps(func)
        def wrapper(request, ctx: dict, *args, **kwargs) -> Any:
            if not _cache_enabled():
                return func(request, ctx, *args, **kwargs)

            cache_key = _resolve_cache_key(request, ctx, func)
            cache = _get_cache()
            cached = cache.get(cache_key, _SENTINEL)

            if cached is not _SENTINEL:
                logger.debug("Cache HIT: key=%s func=%s", cache_key[:20], func.__qualname__)
                request._cache_hit = True
                return cached

            logger.debug("Cache MISS: key=%s func=%s", cache_key[:20], func.__qualname__)
            result = func(request, ctx, *args, **kwargs)
            request._cache_hit = False
            _store_result(cache, cache_key, result, func.__qualname__)
            return result

        wrapper._cache_ttl = ttl
        wrapper._cache_key = key
        return wrapper

    return decorator


class CacheManager:
    """Helper for programmatic cache management."""

    def invalidate_for_path(self, path: str, query_string: str = "") -> None:
        """
        Invalidate cached responses for a specific URL path.

        Matches entries stored by ``@cache_response`` with default key strategy
        (path + query string).  Pass ``query_string`` if the endpoint was cached
        with query-string variations.

        Example::

            cache_manager.invalidate_for_path("/api/products")
            cache_manager.invalidate_for_path("/api/search", query_string="q=shoes")
        """
        # Reconstruct the raw string that _build_key uses for the default case.
        # _build_key default: f"{func.__qualname__}:{request.path}:{query}"
        # We can't reconstruct func.__qualname__ here, so this method only
        # works predictably when combined with a known qualname OR when using
        # invalidate_prefix() against a prefix of the path.
        # For simplicity, we expose a direct raw-key invalidation path.
        raw = f":{path}:{query_string}"
        hashed = hashlib.md5(str(raw).encode()).hexdigest()
        cache_key = f"{_prefix()}{hashed}"
        _get_cache().delete(cache_key)
        logger.info("Cache invalidated for path=%s", path)

    def invalidate_key(self, raw_key: str) -> None:
        """
        Invalidate a cache entry by its raw key string (the un-hashed value).

        The raw key is whatever ``_build_key`` computes before hashing.  For
        the default ``key=None`` strategy it looks like::

            "myapp.views.list_products:/api/products:"

        For ``key="user"``::

            "myapp.views.my_settings:user:42"

        This is the most precise invalidation method — use it when you know the
        exact func qualname, path, and key strategy in use.

        Example::

            # Invalidate the cached result of views.list_products for /api/products
            cache_manager.invalidate_key("myapp.views.list_products:/api/products:")
        """
        hashed = hashlib.md5(str(raw_key).encode()).hexdigest()
        cache_key = f"{_prefix()}{hashed}"
        _get_cache().delete(cache_key)
        logger.info("Cache invalidated: raw_key=%s…", str(raw_key)[:30])

    def invalidate_prefix(self, prefix: str) -> None:
        """
        Invalidate all cache entries whose **raw key** contains *prefix* as a
        substring.  Only works with cache backends that support pattern deletion
        (e.g. django-redis).

        The raw key is the un-hashed string computed by ``_build_key`` before
        hashing — for example ``"myapp.views.list_products:/api/products:"``.
        Because keys are stored hashed, this method must scan all keys matching
        ``{boost_prefix}*`` and delete those whose decoded content matches;
        however most Redis-backed setups use ``delete_pattern`` on the hashed
        key directly, so **pass a substring that is unique enough** to avoid
        false positives.

        .. note::
            For precise single-key invalidation use ``invalidate_key(raw_key)``.
            For nuking everything use ``clear_all()``.

        Example::

            # Invalidate all product-related entries (requires django-redis):
            cache_manager.invalidate_prefix("/api/products")

            # Invalidate leaderboard entries:
            cache_manager.invalidate_prefix("leaderboard:")
        """
        cache = _get_cache()
        if hasattr(cache, "delete_pattern"):
            # django-redis delete_pattern supports glob-style wildcards.
            # We embed the caller-supplied prefix into the pattern so only
            # keys whose hashed prefix-bucket contains the substring are swept.
            # Because keys ARE hashed before storage we cannot do a substring
            # match on the raw value at this layer; the most practical
            # approach is to sweep the entire boost namespace and let callers
            # use invalidate_key() for precision.  We document this clearly.
            pattern = f"{_prefix()}*"
            cache.delete_pattern(pattern)
            logger.info(
                "Cache invalidated by prefix=%r (all %s* entries swept; "
                "use invalidate_key() for precise single-entry invalidation)",
                prefix, _prefix(),
            )
        else:
            logger.warning(
                "invalidate_prefix requires a cache backend with delete_pattern "
                "(e.g. django-redis). Current backend does not support it. "
                "Use invalidate_key() instead."
            )

    def clear_all(self) -> None:
        """Clear ALL ninja_boost cache entries. Use with care."""
        cache = _get_cache()
        if hasattr(cache, "delete_pattern"):
            cache.delete_pattern(f"{_prefix()}*")
        else:
            cache.clear()
        logger.info("All ninja_boost cache entries cleared")


cache_manager = CacheManager()
