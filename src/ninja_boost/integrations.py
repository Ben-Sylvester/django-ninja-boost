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


# ── Production-grade JWT auth ─────────────────────────────────────────────

class JWTAuth(HttpBearer):
    """
    Production-ready JWT bearer auth using PyJWT.

    Install PyJWT::
        pip install PyJWT

    Configuration via settings.py::

        NINJA_BOOST = {
            "AUTH": "ninja_boost.integrations.JWTAuth",
            ...
        }

        # And add JWT settings:
        JWT_SECRET_KEY  = env("JWT_SECRET_KEY")   # or use SECRET_KEY
        JWT_ALGORITHM   = "HS256"                  # or "RS256" for asymmetric
        JWT_EXPIRY_MINS = 60                       # token lifetime in minutes

    Issuing tokens (in a login view)::

        from ninja_boost.integrations import create_jwt_token

        @router.post("/login", auth=None, paginate=False)
        def login(request, ctx, payload: LoginPayload):
            user = authenticate(request, **payload.dict())
            if user is None:
                raise HttpError(401, "Invalid credentials.")
            token = create_jwt_token({"user_id": user.id, "is_staff": user.is_staff})
            return {"access_token": token, "token_type": "bearer"}

    The decoded payload is returned from ``authenticate`` and becomes
    ``request.auth`` / ``ctx["user"]`` in every view.
    """

    def authenticate(self, request, token: str):
        try:
            import jwt as _jwt
        except ImportError as exc:
            raise RuntimeError(
                "JWTAuth requires PyJWT. Install with: pip install PyJWT"
            ) from exc

        from django.conf import settings as djsettings
        secret    = getattr(djsettings, "JWT_SECRET_KEY", djsettings.SECRET_KEY)
        algorithm = getattr(djsettings, "JWT_ALGORITHM",   "HS256")

        try:
            payload = _jwt.decode(token, secret, algorithms=[algorithm])
            return payload
        except _jwt.ExpiredSignatureError:
            return None
        except _jwt.InvalidTokenError:
            return None


def create_jwt_token(payload: dict, expires_minutes: int | None = None) -> str:
    """
    Create a signed JWT token.

    Parameters
    ----------
    payload:
        Data to encode (e.g. ``{"user_id": 42, "is_staff": False}``).
    expires_minutes:
        Override the default expiry. Reads ``JWT_EXPIRY_MINS`` from settings
        if not provided (default: 60 minutes).

    Returns a signed JWT string.

    Example::

        from ninja_boost.integrations import create_jwt_token

        token = create_jwt_token({"user_id": user.id, "username": user.username})
        # "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
    """
    import datetime
    try:
        import jwt as _jwt
    except ImportError as exc:
        raise RuntimeError("create_jwt_token requires PyJWT: pip install PyJWT") from exc

    from django.conf import settings as djsettings
    secret  = getattr(djsettings, "JWT_SECRET_KEY", djsettings.SECRET_KEY)
    algo    = getattr(djsettings, "JWT_ALGORITHM",   "HS256")
    minutes = expires_minutes or getattr(djsettings, "JWT_EXPIRY_MINS", 60)

    data = dict(payload)
    now = datetime.datetime.now(datetime.timezone.utc)
    data["exp"] = now + datetime.timedelta(minutes=minutes)
    data["iat"] = now
    return _jwt.encode(data, secret, algorithm=algo)
