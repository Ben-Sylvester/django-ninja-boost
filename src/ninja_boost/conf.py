"""
ninja_boost.conf
~~~~~~~~~~~~~~~~
Centralised settings proxy with safe defaults and lazy loading.

Configure via ``settings.NINJA_BOOST`` (all keys optional — defaults work
out of the box). The proxy resolves and caches each dotted-path string on
first access; no import overhead on subsequent requests.

Full reference::

    NINJA_BOOST = {
        # ── Core ──────────────────────────────────────────────────────────
        "AUTH":             "ninja_boost.integrations.BearerTokenAuth",
        "RESPONSE_WRAPPER": "ninja_boost.responses.wrap_response",
        "PAGINATION":       "ninja_boost.pagination.auto_paginate",
        "DI":               "ninja_boost.dependencies.inject_context",

        # ── Rate limiting ─────────────────────────────────────────────────
        "RATE_LIMIT": {
            "DEFAULT":  None,          # e.g. "200/minute" — applied to all routes
            "BACKEND":  "ninja_boost.rate_limiting.InMemoryBackend",
        },

        # ── Metrics ───────────────────────────────────────────────────────
        "METRICS": {
            "BACKEND":   None,         # e.g. "ninja_boost.metrics.PrometheusBackend"
            "NAMESPACE": "ninja_boost",
        },

        # ── Docs hardening ────────────────────────────────────────────────
        "DOCS": {
            "ENABLED":               True,
            "REQUIRE_STAFF":         False,
            "REQUIRE_AUTH":          False,
            "ALLOWED_IPS":           [],
            "DISABLE_IN_PRODUCTION": False,
        },

        # ── Plugins (auto-loaded on startup) ──────────────────────────────
        "PLUGINS": [
            # "myproject.plugins.AuditPlugin",
        ],

        # ── Policies (auto-loaded on startup) ─────────────────────────────
        "POLICIES": [
            # "apps.orders.policies.OrderPolicy",
        ],

        # ── Services (auto-loaded on startup) ─────────────────────────────
        "SERVICES": [
            # "apps.users.services.UserService",
        ],
    }
"""

from django.utils.module_loading import import_string


DEFAULTS = {
    "AUTH":             "ninja_boost.integrations.BearerTokenAuth",
    "RESPONSE_WRAPPER": "ninja_boost.responses.wrap_response",
    "PAGINATION":       "ninja_boost.pagination.auto_paginate",
    "DI":               "ninja_boost.dependencies.inject_context",
}

# Keys that are dicts/lists rather than dotted-path strings
_NON_IMPORT_KEYS = {"RATE_LIMIT", "METRICS", "DOCS", "PLUGINS", "POLICIES", "SERVICES"}


class BoostSettings:
    """Lazy proxy around NINJA_BOOST that falls back to built-in defaults."""

    _cache: dict = {}

    def _resolve(self, key: str):
        if key not in self._cache:
            from django.conf import settings
            user = getattr(settings, "NINJA_BOOST", {})
            dotted = user.get(key) or DEFAULTS.get(key)
            if dotted is None:
                raise ValueError(f"No default defined for NINJA_BOOST[{key!r}]")
            self._cache[key] = import_string(dotted)
        return self._cache[key]

    def get(self, key: str, default=None):
        """Return raw (non-import) setting value by key."""
        from django.conf import settings
        cfg = getattr(settings, "NINJA_BOOST", {})
        return cfg.get(key, default)

    @property
    def AUTH(self):             return self._resolve("AUTH")
    @property
    def RESPONSE_WRAPPER(self): return self._resolve("RESPONSE_WRAPPER")
    @property
    def PAGINATION(self):       return self._resolve("PAGINATION")
    @property
    def DI(self):               return self._resolve("DI")

    def reload(self):
        """Clear the import cache — useful in tests or settings overrides."""
        self._cache.clear()


boost_settings = BoostSettings()
