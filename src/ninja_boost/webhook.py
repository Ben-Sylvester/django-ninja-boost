"""
ninja_boost.webhook
~~~~~~~~~~~~~~~~~~~~
Webhook signature verification — validate that incoming webhook payloads
originate from the expected provider and haven't been tampered with.

Supports out-of-the-box verification for:
    - Stripe    (Stripe-Signature header, HMAC-SHA256)
    - GitHub    (X-Hub-Signature-256 header, HMAC-SHA256)
    - Slack     (X-Slack-Signature, v0=HMAC-SHA256 with timestamp)
    - Generic   (any HMAC-SHA256 or HMAC-SHA1 header pattern)

Usage::

    from ninja_boost.webhook import verify_webhook, stripe_webhook, github_webhook

    # Generic HMAC-SHA256:
    @router.post("/webhooks/generic")
    @verify_webhook(secret="WEBHOOK_SECRET", header="X-Signature")
    def handle_webhook(request, ctx, payload: dict): ...

    # Stripe:
    @router.post("/webhooks/stripe")
    @stripe_webhook(secret="STRIPE_WEBHOOK_SECRET")
    def handle_stripe(request, ctx):
        event = json.loads(request.body)
        if event["type"] == "payment_intent.succeeded":
            ...

    # GitHub:
    @router.post("/webhooks/github")
    @github_webhook(secret="GITHUB_WEBHOOK_SECRET")
    def handle_github(request, ctx):
        event = request.headers.get("X-GitHub-Event")
        ...

    # Slack:
    @router.post("/webhooks/slack")
    @slack_webhook(signing_secret="SLACK_SIGNING_SECRET")
    def handle_slack(request, ctx): ...

Security notes
--------------
- All comparisons use ``hmac.compare_digest`` to prevent timing attacks.
- Stripe and Slack verify the timestamp to reject replayed webhooks.
- Secrets should come from environment variables, never hardcoded.

Environment-variable secret loading::

    @stripe_webhook(secret_env="STRIPE_WEBHOOK_SECRET")
    def handle_stripe(request, ctx): ...
    # Reads os.environ["STRIPE_WEBHOOK_SECRET"] at request time.
"""

import hashlib
import hmac
import os
import time
import logging
from functools import wraps
from typing import Any, Callable

from ninja.errors import HttpError

logger = logging.getLogger("ninja_boost.webhook")

_REPLAY_WINDOW_SECONDS = 300  # 5 minutes


# ── Helpers ───────────────────────────────────────────────────────────────

def _get_secret(secret: str | None, secret_env: str | None) -> bytes:
    """Resolve secret from literal or env var."""
    if secret_env:
        val = os.environ.get(secret_env)
        if not val:
            raise RuntimeError(
                f"Environment variable {secret_env!r} is not set. "
                "Cannot verify webhook signature."
            )
        return val.encode()
    if secret:
        return secret.encode() if isinstance(secret, str) else secret
    raise ValueError("Either 'secret' or 'secret_env' must be provided.")


def _hmac_digest(secret: bytes, data: bytes, algorithm: str = "sha256") -> str:
    h = hmac.new(secret, data, getattr(hashlib, algorithm))
    return h.hexdigest()


def _safe_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.lower(), b.lower())


# ── Generic HMAC decorator ────────────────────────────────────────────────

def verify_webhook(
    secret: str | None = None,
    secret_env: str | None = None,
    header: str = "X-Signature",
    algorithm: str = "sha256",
    prefix: str = "",
):
    """
    Generic HMAC-SHA256 (or SHA1) webhook verification decorator.

    Parameters
    ----------
    secret:
        Literal webhook secret string.
    secret_env:
        Environment variable name holding the secret (preferred).
    header:
        Request header containing the signature. Default: ``X-Signature``.
    algorithm:
        ``"sha256"`` (default) or ``"sha1"``.
    prefix:
        Expected prefix in the header value, e.g. ``"sha256="`` for GitHub.

    Example::

        @router.post("/webhooks/myservice")
        @verify_webhook(secret_env="MY_WEBHOOK_SECRET", header="X-My-Sig")
        def handle(request, ctx):
            payload = json.loads(request.body)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(request, ctx: dict, *args, **kwargs) -> Any:
            sig_header = request.headers.get(header, "")
            if not sig_header:
                logger.warning("Webhook: missing %s header from %s", header, ctx.get("ip"))
                raise HttpError(400, "Missing webhook signature header.")

            resolved_secret = _get_secret(secret, secret_env)
            expected = _hmac_digest(resolved_secret, request.body, algorithm)
            received = sig_header.removeprefix(prefix).removeprefix(f"{algorithm}=")

            if not _safe_compare(expected, received):
                logger.warning(
                    "Webhook: signature mismatch from %s [path=%s]",
                    ctx.get("ip"), request.path,
                )
                raise HttpError(401, "Invalid webhook signature.")

            return func(request, ctx, *args, **kwargs)
        return wrapper
    return decorator


# ── Stripe ────────────────────────────────────────────────────────────────

def stripe_webhook(
    secret: str | None = None,
    secret_env: str | None = "STRIPE_WEBHOOK_SECRET",
    tolerance: int = _REPLAY_WINDOW_SECONDS,
):
    """
    Stripe webhook signature verification.

    Validates the ``Stripe-Signature`` header using Stripe's documented
    algorithm (timestamp + payload HMAC-SHA256) and rejects replays.

    Example::

        @router.post("/webhooks/stripe")
        @stripe_webhook()        # reads STRIPE_WEBHOOK_SECRET env var
        def handle_stripe(request, ctx):
            import json
            event = json.loads(request.body)
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(request, ctx: dict, *args, **kwargs) -> Any:
            sig_header = request.headers.get("Stripe-Signature", "")
            if not sig_header:
                raise HttpError(400, "Missing Stripe-Signature header.")

            # Parse the header: t=timestamp,v1=sig1,v1=sig2,...
            parts = dict(p.split("=", 1) for p in sig_header.split(",") if "=" in p)
            ts    = parts.get("t")
            sigs  = [v for k, v in parts.items() if k == "v1"]

            if not ts or not sigs:
                raise HttpError(400, "Malformed Stripe-Signature header.")

            # Replay attack protection
            try:
                ts_int = int(ts)
                if abs(time.time() - ts_int) > tolerance:
                    raise HttpError(400, "Webhook timestamp too old — possible replay attack.")
            except ValueError:
                raise HttpError(400, "Invalid Stripe-Signature timestamp.")

            resolved_secret = _get_secret(secret, secret_env)
            signed_payload  = f"{ts}.".encode() + request.body
            expected = _hmac_digest(resolved_secret, signed_payload, "sha256")

            if not any(_safe_compare(expected, sig) for sig in sigs):
                logger.warning("Stripe webhook: signature mismatch from %s", ctx.get("ip"))
                raise HttpError(401, "Invalid Stripe webhook signature.")

            return func(request, ctx, *args, **kwargs)
        return wrapper
    return decorator


# ── GitHub ────────────────────────────────────────────────────────────────

def github_webhook(
    secret: str | None = None,
    secret_env: str | None = "GITHUB_WEBHOOK_SECRET",
):
    """
    GitHub webhook signature verification.

    Validates the ``X-Hub-Signature-256`` header.

    Example::

        @router.post("/webhooks/github")
        @github_webhook()     # reads GITHUB_WEBHOOK_SECRET env var
        def handle_github(request, ctx):
            event = request.headers.get("X-GitHub-Event", "unknown")
            ...
    """
    return verify_webhook(
        secret=secret,
        secret_env=secret_env,
        header="X-Hub-Signature-256",
        algorithm="sha256",
        prefix="sha256=",
    )


# ── Slack ─────────────────────────────────────────────────────────────────

def slack_webhook(
    signing_secret: str | None = None,
    secret_env: str | None = "SLACK_SIGNING_SECRET",
    tolerance: int = _REPLAY_WINDOW_SECONDS,
):
    """
    Slack webhook signature verification.

    Validates ``X-Slack-Signature`` with Slack's v0 scheme and rejects
    requests older than *tolerance* seconds (default: 5 minutes).

    Example::

        @router.post("/webhooks/slack")
        @slack_webhook()      # reads SLACK_SIGNING_SECRET env var
        def handle_slack(request, ctx): ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(request, ctx: dict, *args, **kwargs) -> Any:
            timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
            sig_header = request.headers.get("X-Slack-Signature", "")

            if not timestamp or not sig_header:
                raise HttpError(400, "Missing Slack signature headers.")

            try:
                ts_int = int(timestamp)
                if abs(time.time() - ts_int) > tolerance:
                    raise HttpError(400, "Slack webhook: timestamp too old.")
            except ValueError:
                raise HttpError(400, "Invalid Slack-Request-Timestamp.")

            resolved_secret = _get_secret(signing_secret, secret_env)
            basestring = f"v0:{timestamp}:".encode() + request.body
            expected = "v0=" + _hmac_digest(resolved_secret, basestring, "sha256")

            if not _safe_compare(expected, sig_header):
                logger.warning("Slack webhook: signature mismatch from %s", ctx.get("ip"))
                raise HttpError(401, "Invalid Slack webhook signature.")

            return func(request, ctx, *args, **kwargs)
        return wrapper
    return decorator
