"""
ninja_boost.conf
~~~~~~~~~~~~~~~~
Centralised settings proxy with safe defaults.

Configure via ``settings.NINJA_BOOST`` (all keys optional — defaults work
out of the box)::

    NINJA_BOOST = {
        "AUTH":             "ninja_boost.integrations.BearerTokenAuth",
        "RESPONSE_WRAPPER": "ninja_boost.responses.wrap_response",
        "PAGINATION":       "ninja_boost.pagination.auto_paginate",
        "DI":               "ninja_boost.dependencies.inject_context",
    }
"""

from django.utils.module_loading import import_string


DEFAULTS = {
    "AUTH":             "ninja_boost.integrations.BearerTokenAuth",
    "RESPONSE_WRAPPER": "ninja_boost.responses.wrap_response",
    "PAGINATION":       "ninja_boost.pagination.auto_paginate",
    "DI":               "ninja_boost.dependencies.inject_context",
}


class BoostSettings:
    """Lazy proxy around NINJA_BOOST that falls back to built-in defaults."""

    _cache: dict = {}

    def _resolve(self, key: str):
        if key not in self._cache:
            from django.conf import settings
            user = getattr(settings, "NINJA_BOOST", {})
            self._cache[key] = import_string(user.get(key) or DEFAULTS[key])
        return self._cache[key]

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
