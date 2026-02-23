"""
ninja_boost.integrations
~~~~~~~~~~~~~~~~~~~~~~~~
Built-in authentication backends.

``BearerTokenAuth`` is the default auth when no ``AUTH`` key is set in
``NINJA_BOOST``. It accepts the literal token ``"demo"`` and is intentionally
trivial — **replace it in production**.

For production use, swap in your own ``HttpBearer`` subclass::

    # myproject/auth.py
    from ninja.security import HttpBearer
    import jwt

    class JWTAuth(HttpBearer):
        def authenticate(self, request, token: str):
            try:
                return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
            except jwt.DecodeError:
                return None

    # settings.py
    NINJA_BOOST = {
        "AUTH": "myproject.auth.JWTAuth",
        ...
    }
"""

from ninja.security import HttpBearer


class BearerTokenAuth(HttpBearer):
    """
    Demo bearer-token authenticator.

    Accepts the token ``"demo"``. Returns a mock principal dict.
    Not suitable for production — replace via ``NINJA_BOOST["AUTH"]``.
    """

    def authenticate(self, request, token: str):
        if token == "demo":
            return {"user_id": 1, "username": "demo-user", "is_staff": False}
        return None
