"""
ninja_boost.security_headers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Security response headers middleware with sane, opinionated production defaults.

A single middleware that sets all the headers security scanners (OWASP ZAP,
Mozilla Observatory, Qualys SSL Labs) look for. Zero configuration required —
defaults are safe for any JSON API. Every header is independently tunable.

Headers set by default
----------------------
    Strict-Transport-Security  max-age=31536000; includeSubDomains
    X-Content-Type-Options     nosniff
    X-Frame-Options            DENY
    Referrer-Policy            strict-origin-when-cross-origin
    Permissions-Policy         camera=(), microphone=(), geolocation=()
    Cache-Control              no-store  (API responses should never be cached by intermediaries)
    Content-Security-Policy    default-src 'none'  (API — no assets to load)
    Cross-Origin-Opener-Policy same-origin
    Cross-Origin-Resource-Policy same-origin

Quick setup — add to MIDDLEWARE after SecurityMiddleware::

    MIDDLEWARE = [
        "django.middleware.security.SecurityMiddleware",
        "ninja_boost.security_headers.SecurityHeadersMiddleware",
        ...
    ]

Full configuration via settings::

    NINJA_BOOST = {
        "SECURITY_HEADERS": {
            # Strict-Transport-Security
            "HSTS_SECONDS":           31536000,       # 0 to disable
            "HSTS_INCLUDE_SUBDOMAINS": True,
            "HSTS_PRELOAD":            False,

            # Content-Security-Policy  (None = use default API policy)
            "CSP":                    "default-src 'none'",

            # X-Frame-Options  ("DENY" | "SAMEORIGIN" | None to disable)
            "X_FRAME_OPTIONS":        "DENY",

            # Referrer-Policy
            "REFERRER_POLICY":        "strict-origin-when-cross-origin",

            # Permissions-Policy
            "PERMISSIONS_POLICY":     "camera=(), microphone=(), geolocation=()",

            # Cache-Control for API responses
            "CACHE_CONTROL":          "no-store",

            # Cross-Origin-Opener-Policy
            "COOP":                   "same-origin",

            # Cross-Origin-Resource-Policy
            "CORP":                   "same-origin",

            # X-Content-Type-Options (True/False)
            "NOSNIFF":                True,

            # Paths to skip (e.g. health endpoints, media serving)
            "SKIP_PATHS":             ["/health", "/ready", "/live"],
        }
    }

Per-response override (for views that serve downloadable content)::

    from ninja_boost.security_headers import with_headers

    @router.get("/download")
    @with_headers({"Cache-Control": "private, max-age=3600",
                   "Content-Disposition": "attachment"})
    def download(request, ctx): ...
"""

import fnmatch
import logging
from functools import wraps
from typing import Any, Callable

logger = logging.getLogger("ninja_boost.security")

# ── Defaults ──────────────────────────────────────────────────────────────

DEFAULTS: dict[str, Any] = {
    "HSTS_SECONDS":            31536000,
    "HSTS_INCLUDE_SUBDOMAINS": True,
    "HSTS_PRELOAD":            False,
    "CSP":                     "default-src 'none'",
    "X_FRAME_OPTIONS":         "DENY",
    "REFERRER_POLICY":         "strict-origin-when-cross-origin",
    "PERMISSIONS_POLICY":      "camera=(), microphone=(), geolocation=()",
    "CACHE_CONTROL":           "no-store",
    "COOP":                    "same-origin",
    "CORP":                    "same-origin",
    "NOSNIFF":                 True,
    "SKIP_PATHS":              ["/health", "/ready", "/live"],
}


def _settings() -> dict:
    from django.conf import settings
    cfg = getattr(settings, "NINJA_BOOST", {})
    merged = dict(DEFAULTS)
    merged.update(cfg.get("SECURITY_HEADERS", {}))
    return merged


def _should_skip(path: str, skip_paths: list[str]) -> bool:
    for pattern in skip_paths:
        if path == pattern or path.startswith(pattern + "/") or fnmatch.fnmatch(path, pattern):
            return True
    return False


def _build_hsts(cfg: dict) -> str | None:
    seconds = cfg.get("HSTS_SECONDS", 0)
    if not seconds:
        return None
    value = f"max-age={seconds}"
    if cfg.get("HSTS_INCLUDE_SUBDOMAINS"):
        value += "; includeSubDomains"
    if cfg.get("HSTS_PRELOAD"):
        value += "; preload"
    return value


# ── Middleware ────────────────────────────────────────────────────────────

class SecurityHeadersMiddleware:
    """
    Django WSGI/ASGI middleware that sets security response headers.

    Reads configuration from ``settings.NINJA_BOOST["SECURITY_HEADERS"]``.
    Skips health check paths by default. Safe to use alongside Django's own
    ``SecurityMiddleware`` — they set non-overlapping headers.
    """

    async_capable = True
    sync_capable  = True

    def __init__(self, get_response):
        import asyncio
        self.get_response = get_response
        self._is_async    = asyncio.iscoroutinefunction(get_response)

    def __call__(self, request):
        if self._is_async:
            return self.__acall__(request)
        return self._sync_call(request)

    def _sync_call(self, request):
        response = self.get_response(request)
        cfg = _settings()
        if not _should_skip(request.path, cfg.get("SKIP_PATHS", [])):
            _apply_headers(response, cfg)
        # Apply per-view header overrides set by @with_headers decorator
        _apply_extra_headers(request, response)
        return response

    async def __acall__(self, request):
        response = await self.get_response(request)
        cfg = _settings()
        if not _should_skip(request.path, cfg.get("SKIP_PATHS", [])):
            _apply_headers(response, cfg)
        # Apply per-view header overrides set by @with_headers decorator
        _apply_extra_headers(request, response)
        return response


def _apply_extra_headers(request, response) -> None:
    """
    Apply per-view header overrides stored by the ``@with_headers`` decorator.

    The decorator stores ``{header: value}`` on ``request._boost_extra_headers``.
    These override (or extend) the global security headers set by the middleware.
    """
    extra = getattr(request, "_boost_extra_headers", None)
    if extra:
        for key, value in extra.items():
            response[key] = value


def _apply_headers(response, cfg: dict) -> None:
    """Write all configured security headers onto *response*."""

    # Strict-Transport-Security
    hsts = _build_hsts(cfg)
    if hsts:
        response.setdefault("Strict-Transport-Security", hsts)

    # X-Content-Type-Options
    if cfg.get("NOSNIFF", True):
        response.setdefault("X-Content-Type-Options", "nosniff")

    # X-Frame-Options
    xfo = cfg.get("X_FRAME_OPTIONS")
    if xfo:
        response.setdefault("X-Frame-Options", xfo)

    # Content-Security-Policy
    csp = cfg.get("CSP")
    if csp:
        response.setdefault("Content-Security-Policy", csp)

    # Referrer-Policy
    rp = cfg.get("REFERRER_POLICY")
    if rp:
        response.setdefault("Referrer-Policy", rp)

    # Permissions-Policy
    pp = cfg.get("PERMISSIONS_POLICY")
    if pp:
        response.setdefault("Permissions-Policy", pp)

    # Cache-Control (API responses should not be cached by intermediaries)
    cc = cfg.get("CACHE_CONTROL")
    if cc and "Cache-Control" not in response:
        response["Cache-Control"] = cc

    # Cross-Origin-Opener-Policy
    coop = cfg.get("COOP")
    if coop:
        response.setdefault("Cross-Origin-Opener-Policy", coop)

    # Cross-Origin-Resource-Policy
    corp = cfg.get("CORP")
    if corp:
        response.setdefault("Cross-Origin-Resource-Policy", corp)

    # Always remove the Server header if present (information leakage)
    if "Server" in response:
        del response["Server"]

    # Always remove X-Powered-By if present
    if "X-Powered-By" in response:
        del response["X-Powered-By"]


# ── Per-view decorator ────────────────────────────────────────────────────

def with_headers(headers: dict[str, str]):
    """
    Decorator: set specific response headers on a single view.

    Use to override the global security defaults for one route
    (e.g. a download endpoint that needs a different Cache-Control).

    Example::

        @router.get("/export")
        @with_headers({
            "Cache-Control": "private, max-age=300",
            "Content-Disposition": "attachment; filename=export.csv",
        })
        def export(request, ctx): ...
    """
    def decorator(func: Callable) -> Callable:
        import asyncio

        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(request, *args, **kwargs) -> Any:
                result = await func(request, *args, **kwargs)
                # Headers will be set by the middleware; store on request for now
                if not hasattr(request, "_boost_extra_headers"):
                    request._boost_extra_headers = {}
                request._boost_extra_headers.update(headers)
                return result
            return async_wrapper

        @wraps(func)
        def sync_wrapper(request, *args, **kwargs) -> Any:
            result = func(request, *args, **kwargs)
            if not hasattr(request, "_boost_extra_headers"):
                request._boost_extra_headers = {}
            request._boost_extra_headers.update(headers)
            return result
        return sync_wrapper

    return decorator


# ── Security report ───────────────────────────────────────────────────────

def security_report() -> dict[str, Any]:
    """
    Return a dict describing the current security header configuration.
    Useful for a ``/admin/security`` diagnostic endpoint or in tests.

    Example::

        from ninja_boost.security_headers import security_report
        print(security_report())
    """
    cfg  = _settings()
    hsts = _build_hsts(cfg)
    return {
        "hsts":               hsts,
        "csp":                cfg.get("CSP"),
        "x_frame_options":    cfg.get("X_FRAME_OPTIONS"),
        "referrer_policy":    cfg.get("REFERRER_POLICY"),
        "permissions_policy": cfg.get("PERMISSIONS_POLICY"),
        "cache_control":      cfg.get("CACHE_CONTROL"),
        "coop":               cfg.get("COOP"),
        "corp":               cfg.get("CORP"),
        "nosniff":            cfg.get("NOSNIFF", True),
        "skip_paths":         cfg.get("SKIP_PATHS", []),
    }
