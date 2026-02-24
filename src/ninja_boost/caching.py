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

    cache_manager.invalidate("path", "/api/products")
    cache_manager.invalidate_prefix("leaderboard:")
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
from functools import wraps
from typing import Any, Callable

logger = logging.getLogger("ninja_boost.caching")

_SENTINEL = object()


def _is_queryset(obj) -> bool:
    """Detect Django QuerySets without importing the ORM (avoids circular deps)."""
    return hasattr(obj, "count") and hasattr(obj, "filter") and hasattr(obj, "values")


def _get_cache():
    from django.core.cache import caches
    from django.conf import settings
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
        uid  = user.get("id") or user.get("user_id") if isinstance(user, dict) else getattr(user, "id", None)
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
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(request, ctx: dict, *args, **kwargs) -> Any:
            if not _cache_enabled():
                return func(request, ctx, *args, **kwargs)

            # Build cache key
            cache_key = _build_key(key, request, ctx, func)

            # Vary on headers
            if vary_on_headers:
                header_bits = ":".join(
                    request.META.get(f"HTTP_{h.upper().replace('-', '_')}", "")
                    for h in vary_on_headers
                )
                if header_bits:
                    cache_key += f":{hashlib.md5(header_bits.encode()).hexdigest()}"

            cache = _get_cache()
            cached = cache.get(cache_key, _SENTINEL)

            if cached is not _SENTINEL:
                logger.debug("Cache HIT: key=%s func=%s", cache_key[:20], func.__qualname__)
                # Attach cache hit marker for metrics / logging
                request._cache_hit = True
                return cached

            logger.debug("Cache MISS: key=%s func=%s", cache_key[:20], func.__qualname__)
            result = func(request, ctx, *args, **kwargs)
            request._cache_hit = False

            # Evaluate Django QuerySets to lists before caching.
            # QuerySets are lazy database cursors — they are not picklable and
            # would go stale if cached. Materialising to a list makes them
            # safe to store and still paginatable on retrieval.
            if result is not None and _is_queryset(result):
                result = list(result)

            # Only cache successful, non-None results
            if result is not None:
                try:
                    cache.set(cache_key, result, timeout=ttl)
                except Exception:
                    logger.warning(
                        "Cache set failed (result may not be picklable): func=%s",
                        func.__qualname__, exc_info=True,
                    )

            return result

        wrapper._cache_ttl = ttl
        wrapper._cache_key = key
        return wrapper

    return decorator


class CacheManager:
    """Helper for programmatic cache management."""

    def invalidate(self, key_type: str, value: str) -> None:
        """Invalidate a specific cache entry by key type and value."""
        raw = f"{key_type}:{value}"
        hashed = hashlib.md5(raw.encode()).hexdigest()
        cache_key = f"{_prefix()}{hashed}"
        _get_cache().delete(cache_key)
        logger.info("Cache invalidated: key=%s", cache_key[:20])

    def invalidate_prefix(self, prefix: str) -> None:
        """
        Invalidate all keys starting with *prefix*.
        Only works with cache backends that support pattern deletion (Redis).
        """
        cache = _get_cache()
        if hasattr(cache, "delete_pattern"):
            # django-redis provides delete_pattern
            cache.delete_pattern(f"{_prefix()}*{prefix}*")
            logger.info("Cache invalidated by prefix: %s", prefix)
        else:
            logger.warning(
                "invalidate_prefix requires a cache backend with delete_pattern "
                "(e.g. django-redis). Current backend does not support it."
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
