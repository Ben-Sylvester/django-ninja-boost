"""
ninja_boost.api
~~~~~~~~~~~~~~~
AutoAPI — a NinjaAPI subclass with auto-wired auth, response envelope,
plugin lifecycle hooks, event dispatch, and docs hardening.

Drop-in replacement for NinjaAPI::

    # Before:
    from ninja import NinjaAPI
    api = NinjaAPI()

    # After:
    from ninja_boost import AutoAPI
    api = AutoAPI()

Every argument NinjaAPI accepts still works::

    api = AutoAPI(
        title="Bookstore API",
        version="2.0",
        description="Powered by django-ninja-boost",
    )

What AutoAPI adds automatically
---------------------------------
1. Default auth from ``settings.NINJA_BOOST["AUTH"]``
2. Response envelope: ``{"ok": True, "data": <payload>}``
3. Double-wrap prevention on error responses
4. Plugin lifecycle hooks fired on startup
5. Docs access hardening (if ``settings.NINJA_BOOST["DOCS"]`` is configured)
"""

import logging
from typing import Any

from ninja import NinjaAPI

from ninja_boost.conf import boost_settings

logger = logging.getLogger("ninja_boost.api")


class AutoAPI(NinjaAPI):
    """
    Drop-in NinjaAPI subclass with auto-wired auth, response envelope,
    plugin hooks, and event dispatch.
    """

    def __init__(self, *args, **kwargs):
        # ── Auth ──────────────────────────────────────────────────────────
        if "auth" not in kwargs:
            auth_class = boost_settings.AUTH
            kwargs["auth"] = auth_class()

        super().__init__(*args, **kwargs)

        # ── Notify plugins of new API instance ────────────────────────────
        try:
            from ninja_boost.plugins import plugin_registry
            plugin_registry.fire_startup(self)
        except Exception:
            logger.exception("Plugin startup hooks raised")

        # ── Docs hardening ────────────────────────────────────────────────
        try:
            from django.conf import settings as djsettings
            cfg = getattr(djsettings, "NINJA_BOOST", {})
            if "DOCS" in cfg:
                from ninja_boost.docs import harden_docs
                harden_docs(self)
        except Exception:
            logger.debug("Docs hardening skipped (Django not configured)", exc_info=True)

        logger.debug("AutoAPI initialised: title=%r version=%r",
                     getattr(self, "title", None), getattr(self, "version", None))

    def create_response(self, request, data: Any, *args, **kwargs):
        """
        Wrap *data* in the response envelope unless it is already wrapped.

        Error envelopes from exception handlers contain ``"ok"`` already —
        they are passed through as-is to prevent double-wrapping.
        """
        if not isinstance(data, dict) or "ok" not in data:
            data = boost_settings.RESPONSE_WRAPPER(data)
        return super().create_response(request, data, *args, **kwargs)
