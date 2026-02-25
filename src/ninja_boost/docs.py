"""
ninja_boost.docs
~~~~~~~~~~~~~~~~
API documentation hardening, access controls, and OpenAPI customisation.

Django Ninja auto-generates OpenAPI docs at /api/docs and /api/redoc.
In production, you typically want to:
  - Restrict access (require login or internal IP)
  - Disable entirely (for public-facing APIs)
  - Add custom tags, descriptions, and security schemes
  - Inject rate limit and permission metadata into the schema

Usage — basic access restriction::

    from ninja_boost.docs import harden_docs

    api = AutoAPI(title="My API")
    harden_docs(api)         # picks up NINJA_BOOST["DOCS"] from settings

Usage — explicit configuration::

    from ninja_boost.docs import harden_docs, DocGuard

    harden_docs(api, guard=DocGuard(
        require_staff=True,
        allowed_ips=["10.0.0.0/8", "127.0.0.1"],
        disable_in_production=True,
    ))

Settings reference::

    NINJA_BOOST = {
        "DOCS": {
            "ENABLED":               True,      # False → returns 404 for /docs and /redoc
            "REQUIRE_STAFF":         False,      # True → only staff users can view docs
            "REQUIRE_AUTH":          False,      # True → any authenticated user required
            "ALLOWED_IPS":           [],         # ["127.0.0.1", "10.0.0.0/8"] — CIDR supported
            "DISABLE_IN_PRODUCTION": False,      # True → disabled when DEBUG=False
            "TITLE":                 None,       # Override OpenAPI title
            "DESCRIPTION":           None,       # Prepend to OpenAPI description
            "VERSION":               None,       # Override version string
            "TERMS_OF_SERVICE":      None,
            "CONTACT":               None,       # {"name": "...", "email": "...", "url": "..."}
            "LICENSE":               None,       # {"name": "MIT", "url": "..."}
            "SERVERS":               [],         # [{"url": "https://api.example.com"}]
        }
    }
"""

import ipaddress
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("ninja_boost.docs")


# ── Guard configuration ───────────────────────────────────────────────────

@dataclass
class DocGuard:
    """
    Configuration object for docs access control.

    All checks are ANDed — a request must pass ALL enabled checks to see docs.
    """
    enabled:               bool       = True
    require_staff:         bool       = False
    require_auth:          bool       = False
    allowed_ips:           list[str]  = field(default_factory=list)
    disable_in_production: bool       = False
    custom_check:          Callable | None = None  # fn(request) -> bool

    @classmethod
    def from_settings(cls) -> "DocGuard":
        """Build a DocGuard from NINJA_BOOST["DOCS"] settings."""
        from django.conf import settings
        cfg  = getattr(settings, "NINJA_BOOST", {})
        docs = cfg.get("DOCS", {})
        return cls(
            enabled               = docs.get("ENABLED", True),
            require_staff         = docs.get("REQUIRE_STAFF", False),
            require_auth          = docs.get("REQUIRE_AUTH", False),
            allowed_ips           = docs.get("ALLOWED_IPS", []),
            disable_in_production = docs.get("DISABLE_IN_PRODUCTION", False),
            custom_check          = None,
        )

    def is_allowed(self, request) -> bool:
        """Return True if *request* should be allowed to see docs."""
        from django.conf import settings as djsettings

        if not self.enabled:
            return False

        if self.disable_in_production and not djsettings.DEBUG:
            return False

        if self.allowed_ips:
            client_ip = _get_ip(request)
            if not _ip_in_list(client_ip, self.allowed_ips):
                return False

        if self.require_auth or self.require_staff:
            user = getattr(request, "user", None)
            if user is None or not user.is_authenticated:
                return False
            if self.require_staff and not user.is_staff:
                return False

        if self.custom_check is not None:
            try:
                if not self.custom_check(request):
                    return False
            except Exception:
                logger.exception("DocGuard.custom_check raised")
                return False

        return True


# ── IP helpers ────────────────────────────────────────────────────────────

def _get_ip(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "0.0.0.0")


def _ip_in_list(ip_str: str, allowed: list[str]) -> bool:
    try:
        client = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    for entry in allowed:
        try:
            if "/" in entry:
                if client in ipaddress.ip_network(entry, strict=False):
                    return True
            else:
                if client == ipaddress.ip_address(entry):
                    return True
        except ValueError:
            continue
    return False


# ── Main harden function ──────────────────────────────────────────────────

def harden_docs(api: Any, guard: DocGuard | None = None) -> None:
    """
    Apply documentation access controls and OpenAPI enrichment to *api*.

    Call once after constructing your AutoAPI instance::

        api = AutoAPI()
        harden_docs(api)
        register_exception_handlers(api)
    """
    if guard is None:
        guard = DocGuard.from_settings()

    _patch_docs_views(api, guard)
    _enrich_openapi(api)
    logger.info(
        "Docs hardened: enabled=%s require_staff=%s require_auth=%s allowed_ips=%s",
        guard.enabled, guard.require_staff, guard.require_auth, guard.allowed_ips,
    )


def _patch_docs_views(api: Any, guard: DocGuard) -> None:
    """
    Monkey-patch the NinjaAPI instance to gate /docs and /redoc endpoints.

    NinjaAPI exposes get_openapi_schema, docs_view, and redoc_view as methods
    on the instance. We wrap them to enforce the guard.
    """
    from django.http import HttpResponseForbidden, HttpResponseNotFound

    def _guarded(original_view, request, *args, **kwargs):
        if not guard.is_allowed(request):
            logger.warning(
                "Docs access denied: ip=%s staff=%s auth=%s",
                _get_ip(request),
                getattr(getattr(request, "user", None), "is_staff", False),
                getattr(getattr(request, "user", None), "is_authenticated", False),
            )
            if not guard.enabled:
                return HttpResponseNotFound("API documentation is not available.")
            return HttpResponseForbidden("Access to API documentation requires authentication.")
        return original_view(request, *args, **kwargs)

    # NinjaAPI uses self.urls to bind views; we patch the bound view methods
    for attr_name in ("docs_view", "redoc_view"):
        # Always fetch the bound method from the instance, not from type(api).
        # Fetching from type(api) gives an unbound function which lacks `self`,
        # so calling original(request) would fail with a TypeError.
        original = getattr(api, attr_name, None)
        if original is not None and callable(original):
            # Store original and wrap
            setattr(api, f"_boost_original_{attr_name}", original)
            import functools
            guarded = functools.partial(_guarded, original)
            guarded.__name__ = getattr(original, "__name__", attr_name)
            try:
                setattr(api, attr_name, guarded)
            except AttributeError:
                pass  # Some NinjaAPI versions use __slots__ or properties


def _enrich_openapi(api: Any) -> None:
    """Apply DOCS settings to the OpenAPI schema metadata."""
    from django.conf import settings as djsettings
    cfg  = getattr(djsettings, "NINJA_BOOST", {})
    docs = cfg.get("DOCS", {})

    if docs.get("TITLE"):
        try:
            api.title = docs["TITLE"]
        except AttributeError:
            pass

    if docs.get("VERSION"):
        try:
            api.version = docs["VERSION"]
        except AttributeError:
            pass

    extra_desc = docs.get("DESCRIPTION", "")
    if extra_desc:
        try:
            existing = getattr(api, "description", "") or ""
            api.description = f"{extra_desc}\n\n{existing}".strip()
        except AttributeError:
            pass

    if docs.get("SERVERS"):
        try:
            api.servers = docs["SERVERS"]
        except AttributeError:
            pass


# ── OpenAPI schema hooks ──────────────────────────────────────────────────

def add_security_scheme(
    api: Any,
    name: str = "BearerAuth",
    scheme_type: str = "http",
    scheme: str = "bearer",
    bearer_format: str = "JWT",
) -> None:
    """
    Add a named security scheme to the OpenAPI schema.

    Example::

        add_security_scheme(api, "BearerAuth", scheme_type="http",
                            scheme="bearer", bearer_format="JWT")
    """
    original_schema_fn = getattr(api, "get_openapi_schema", None)
    if original_schema_fn is None:
        return

    import functools

    @functools.wraps(original_schema_fn)
    def patched_schema(*args, **kwargs):
        schema = original_schema_fn(*args, **kwargs)
        components = schema.setdefault("components", {})
        security_schemes = components.setdefault("securitySchemes", {})
        security_schemes[name] = {
            "type": scheme_type,
            "scheme": scheme,
            "bearerFormat": bearer_format,
        }
        schema.setdefault("security", []).append({name: []})
        return schema

    api.get_openapi_schema = patched_schema


def add_rate_limit_headers_to_schema(api: Any) -> None:
    """
    Document rate limit response headers in the OpenAPI schema.
    Patches the schema to include X-RateLimit-Limit and X-RateLimit-Remaining.
    """
    original = getattr(api, "get_openapi_schema", None)
    if original is None:
        return

    import functools

    @functools.wraps(original)
    def patched(*args, **kwargs):
        schema = original(*args, **kwargs)
        # Add rate limit headers to every 200 response
        for path_data in schema.get("paths", {}).values():
            for op_data in path_data.values():
                if isinstance(op_data, dict):
                    responses = op_data.setdefault("responses", {})
                    for status_code, resp in responses.items():
                        if str(status_code).startswith("2"):
                            hdrs = resp.setdefault("headers", {})
                            hdrs["X-RateLimit-Limit"] = {
                                "description": "Request limit per window",
                                "schema": {"type": "integer"},
                            }
                            hdrs["X-RateLimit-Remaining"] = {
                                "description": "Remaining requests in current window",
                                "schema": {"type": "integer"},
                            }
        return schema

    api.get_openapi_schema = patched
