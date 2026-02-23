"""
ninja_boost.responses
~~~~~~~~~~~~~~~~~~~~~
Standard success response envelope.

Every successful response from AutoAPI is wrapped as::

    {"ok": True, "data": <payload>}

Error responses use the same shape but ``"ok": False``::

    {"ok": False, "error": "Not found", "code": 404}

Customise by pointing ``NINJA_BOOST["RESPONSE_WRAPPER"]`` at your own callable
with signature ``(data: Any) -> dict``.
"""

from typing import Any


def wrap_response(data: Any) -> dict:
    """Wrap *data* in the standard success envelope."""
    return {"ok": True, "data": data}
