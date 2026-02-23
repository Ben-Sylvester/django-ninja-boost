"""
ninja_boost.api
~~~~~~~~~~~~~~~
AutoAPI — a NinjaAPI subclass with auto-wired auth and response envelope.

How to integrate into an existing Django Ninja project
------------------------------------------------------
One-line change in your urls.py (or wherever you construct the API):

    # Before (vanilla Django Ninja):
    from ninja import NinjaAPI
    api = NinjaAPI()

    # After (with ninja_boost):
    from ninja_boost import AutoAPI
    api = AutoAPI()

That's it. No other files change. AutoAPI is a drop-in subclass — every
argument that NinjaAPI accepts still works::

    api = AutoAPI(
        title="Bookstore API",
        version="2.0",
        description="Powered by django-ninja-boost",
    )

What AutoAPI adds automatically
--------------------------------
1. Default auth from ``settings.NINJA_BOOST["AUTH"]``
   (overridable per-route with ``auth=MyAuth()`` or ``auth=None``)

2. Response envelope on every successful response:
   ``{"ok": True, "data": <your return value>}``

3. Error responses from exception handlers are never double-wrapped.
   They check for the "ok" key and pass through as-is.
"""

from typing import Any
from ninja import NinjaAPI
from ninja_boost.conf import boost_settings


class AutoAPI(NinjaAPI):
    """
    Drop-in NinjaAPI subclass with auto-wired auth + response envelope.

    Parameters match NinjaAPI exactly — add ``title``, ``version``, ``docs``,
    ``urls_namespace``, etc. as needed.
    """

    def __init__(self, *args, **kwargs):
        if "auth" not in kwargs:
            auth_class = boost_settings.AUTH
            kwargs["auth"] = auth_class()
        super().__init__(*args, **kwargs)

    def create_response(self, request, data: Any, *args, **kwargs):
        """
        Wrap data in the response envelope unless it's already an envelope.

        Already-wrapped dicts (those containing the ``"ok"`` key, e.g. from
        exception handlers) are passed through untouched to prevent double-wrapping.
        """
        if not isinstance(data, dict) or "ok" not in data:
            data = boost_settings.RESPONSE_WRAPPER(data)
        return super().create_response(request, data, *args, **kwargs)
