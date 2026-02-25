"""
ninja_boost.rate_limiting
~~~~~~~~~~~~~~~~~~~~~~~~~
Built-in rate limiting with pluggable backends.

Rate limits are expressed as ``"N/period"`` strings:
    "100/hour"   — 100 requests per hour
    "20/minute"  — 20 requests per minute
    "5/second"   — 5 requests per second
    "1000/day"   — 1000 requests per day

Two backends are included:
    InMemoryBackend   — fast, process-local, no dependencies (default)
    CacheBackend      — uses Django's cache framework (Redis, Memcached, etc.)
                        supports multi-process / multi-server deployments

Usage — per-route decorator::

    from ninja_boost.rate_limiting import rate_limit

    @router.get("/search")
    @rate_limit("30/minute")                     # key = client IP
    def search(request, ctx, q: str): ...

    @router.post("/login")
    @rate_limit("5/minute", key="ip")            # explicit IP key
    def login(request, ctx, payload): ...

    @router.post("/send-email")
    @rate_limit("10/hour", key="user")           # key = ctx["user"]["id"]
    def send_email(request, ctx, payload): ...

    @router.get("/data")
    @rate_limit("1000/day", key=lambda req, ctx: f"tenant:{ctx['tenant']}")
    def data(request, ctx): ...                  # custom key function

Global rate limiting via settings::

    NINJA_BOOST = {
        ...
        "RATE_LIMIT": {
            "DEFAULT":  "200/minute",            # applies to every route
            "BACKEND":  "ninja_boost.rate_limiting.InMemoryBackend",
        },
    }

Per-route overrides always win over the global default.
"""

import time
import hashlib
import logging
import threading
from functools import wraps
from typing import Any, Callable

from ninja.errors import HttpError

from ninja_boost.events import event_bus, ON_RATE_LIMIT_EXCEEDED

logger = logging.getLogger("ninja_boost.rate_limit")

# ── Period parsing ─────────────────────────────────────────────────────────

_PERIOD_SECONDS = {
    "second": 1,
    "minute": 60,
    "hour":   3600,
    "day":    86400,
}


def _parse_rate(rate: str) -> tuple[int, int]:
    """Parse ``"N/period"`` → ``(limit, window_seconds)``."""
    try:
        count_str, period = rate.lower().split("/")
        count  = int(count_str.strip())
        window = _PERIOD_SECONDS[period.strip()]
        return count, window
    except (ValueError, KeyError):
        raise ValueError(
            f"Invalid rate string '{rate}'. Expected format: 'N/second|minute|hour|day'"
        )


# ── Backends ───────────────────────────────────────────────────────────────

class InMemoryBackend:
    """
    Process-local rate limiting using a sliding window counter.

    Thread-safe. Suitable for single-process deployments (gunicorn --workers 1,
    development, tests). For multi-process deployments use CacheBackend.
    """

    def __init__(self):
        self._store: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def is_allowed(self, key: str, limit: int, window: int) -> tuple[bool, int, int]:
        """
        Check if the request is within the rate limit.

        Returns:
            (allowed, remaining, retry_after_seconds)
        """
        now = time.time()
        cutoff = now - window

        with self._lock:
            timestamps = self._store.get(key, [])
            # Slide the window — discard timestamps older than the window
            timestamps = [t for t in timestamps if t > cutoff]

            if len(timestamps) >= limit:
                oldest    = timestamps[0]
                retry_after = int(window - (now - oldest)) + 1
                self._store[key] = timestamps
                return False, 0, retry_after

            timestamps.append(now)
            self._store[key] = timestamps
            remaining = limit - len(timestamps)
            return True, remaining, 0

    def cleanup(self) -> int:
        """Remove expired entries. Returns count of keys removed."""
        now = time.time()
        removed = 0
        with self._lock:
            to_delete = []
            for key, timestamps in self._store.items():
                if not timestamps or now - timestamps[-1] > 86400:
                    to_delete.append(key)
            for key in to_delete:
                del self._store[key]
                removed += 1
        return removed


class CacheBackend:
    """
    Rate limiting backed by Django's cache framework.

    Works across multiple processes and servers. Requires a shared cache
    (Redis recommended). Uses atomic increment operations where available.

    Configure the cache in settings.py::

        CACHES = {
            "default": {
                "BACKEND": "django_redis.cache.RedisCache",
                "LOCATION": "redis://localhost:6379/1",
            }
        }
    """

    def __init__(self, cache_alias: str = "default"):
        self._alias = cache_alias

    def is_allowed(self, key: str, limit: int, window: int) -> tuple[bool, int, int]:
        from django.core.cache import caches
        cache = caches[self._alias]

        cache_key = f"boost:rl:{hashlib.md5(key.encode()).hexdigest()}"

        count = cache.get(cache_key, 0)

        if count >= limit:
            # TTL of the key gives approximate retry window
            ttl = cache.ttl(cache_key) if hasattr(cache, "ttl") else window
            return False, 0, int(ttl) + 1

        # Increment atomically
        try:
            new_count = cache.incr(cache_key)
        except ValueError:
            cache.set(cache_key, 1, timeout=window)
            new_count = 1

        if new_count == 1:
            cache.expire(cache_key, window) if hasattr(cache, "expire") else None

        remaining = max(0, limit - new_count)
        return True, remaining, 0


# ── Global backend singleton ──────────────────────────────────────────────

_backend: InMemoryBackend | CacheBackend | None = None
_backend_lock = threading.Lock()


def _get_backend() -> InMemoryBackend | CacheBackend:
    global _backend
    if _backend is None:
        with _backend_lock:
            if _backend is None:
                from django.conf import settings
                from django.utils.module_loading import import_string
                cfg = getattr(settings, "NINJA_BOOST", {})
                rl  = cfg.get("RATE_LIMIT", {})
                dotted = rl.get("BACKEND", "ninja_boost.rate_limiting.InMemoryBackend")
                cls = import_string(dotted)
                _backend = cls()
    return _backend


def _reset_backend() -> None:
    """Reset the backend — used in tests."""
    global _backend
    _backend = None


# ── Key resolvers ─────────────────────────────────────────────────────────

def _resolve_key(key_spec: str | Callable | None, request, ctx: dict) -> str:
    """Turn a key spec into a concrete string key."""
    if callable(key_spec):
        return str(key_spec(request, ctx))
    if key_spec == "user":
        user = ctx.get("user") or {}
        uid  = (user.get("id") or user.get("user_id")) if isinstance(user, dict) else getattr(user, "id", None)
        if uid is None:
            # Fall back to IP for anonymous users
            return f"ip:{ctx.get('ip', 'unknown')}"
        return f"user:{uid}"
    # Default: IP
    ip = ctx.get("ip") or request.META.get("REMOTE_ADDR", "unknown")
    return f"ip:{ip}"


# ── Public decorator ──────────────────────────────────────────────────────

def rate_limit(
    rate: str,
    key: str | Callable | None = None,
    error_message: str = "Rate limit exceeded. Please slow down.",
):
    """
    Decorator: apply a rate limit to a view function.

    Parameters
    ----------
    rate:
        Rate string: ``"N/second|minute|hour|day"``.
    key:
        How to identify the caller. Options:
            ``"ip"``    — client IP address (default)
            ``"user"``  — authenticated user ID (falls back to IP if anonymous)
            callable    — ``fn(request, ctx) -> str``
    error_message:
        Message returned in the 429 response body.

    Example::

        @router.get("/export")
        @rate_limit("10/hour", key="user")
        def export(request, ctx): ...
    """
    limit, window = _parse_rate(rate)

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(request, ctx: dict, *args, **kwargs) -> Any:
            resolved_key = _resolve_key(key, request, ctx)
            bucket_key   = f"{func.__module__}.{func.__qualname__}:{resolved_key}"

            backend = _get_backend()
            allowed, remaining, retry_after = backend.is_allowed(bucket_key, limit, window)

            # Attach rate limit info to request for middleware / logging
            request.rate_limit_remaining = remaining
            request.rate_limit_limit     = limit

            if not allowed:
                event_bus.emit(
                    ON_RATE_LIMIT_EXCEEDED,
                    request=request,
                    ctx=ctx,
                    key=resolved_key,
                    rate=rate,
                    retry_after=retry_after,
                )
                logger.warning(
                    "Rate limit exceeded: key=%s rate=%s retry_after=%ss",
                    resolved_key, rate, retry_after,
                )
                raise HttpError(429, error_message)

            return func(request, ctx, *args, **kwargs)

        # Attach metadata for introspection / docs
        wrapper._rate_limit       = rate
        wrapper._rate_limit_key   = key
        wrapper._rate_limit_limit = limit
        wrapper._rate_limit_window = window
        return wrapper

    return decorator


# ── Global default rate limit (applied by AutoRouter) ─────────────────────

def _get_global_rate() -> str | None:
    """Return the global default rate string from settings, or None."""
    from django.conf import settings
    cfg = getattr(settings, "NINJA_BOOST", {})
    return cfg.get("RATE_LIMIT", {}).get("DEFAULT")


def apply_global_rate_limit(func: Callable, rate: str) -> Callable:
    """Wrap *func* with the global rate limit if it doesn't already have one."""
    if getattr(func, "_rate_limit", None) is not None:
        return func  # per-route limit already applied — don't override
    return rate_limit(rate)(func)
