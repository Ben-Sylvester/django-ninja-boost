"""
ninja_boost.health
~~~~~~~~~~~~~~~~~~~
Production-grade health check endpoints.

Provides two standard health endpoints:

    GET /health/live    — liveness probe (is the process running?)
    GET /health/ready   — readiness probe (is the app ready to serve traffic?)

Liveness is always fast (just returns 200). Readiness runs configurable
checks: database connectivity, cache connectivity, custom checks.

Compatible with Kubernetes liveness/readiness probes, AWS ALB health checks,
GCP Cloud Run, Docker HEALTHCHECK, and monitoring tools.

Usage::

    from ninja_boost.health import health_router
    from ninja_boost import AutoAPI
    from ninja_boost.exceptions import register_exception_handlers

    api = AutoAPI()
    register_exception_handlers(api)
    api.add_router("/health", health_router)

Custom checks::

    from ninja_boost.health import health_router, register_check

    @register_check("redis")
    def check_redis():
        from django.core.cache import cache
        cache.set("health:ping", 1, timeout=5)
        assert cache.get("health:ping") == 1

    @register_check("celery", critical=False)   # non-critical: degraded, not down
    def check_celery():
        from myapp.celery import app
        app.control.ping(timeout=1.0)

Response shape::

    # All checks pass:
    GET /health/ready → 200
    {
        "ok": true,
        "status": "healthy",
        "checks": {
            "database": {"status": "healthy", "duration_ms": 1.2},
            "cache":    {"status": "healthy", "duration_ms": 0.4},
            "redis":    {"status": "healthy", "duration_ms": 0.8}
        },
        "version": "0.2.0"
    }

    # A critical check fails:
    GET /health/ready → 503
    {
        "ok": false,
        "status": "unhealthy",
        "checks": {
            "database": {"status": "unhealthy", "error": "Connection refused", "duration_ms": 5002}
        }
    }

    # A non-critical check fails:
    GET /health/ready → 200
    {
        "ok": true,
        "status": "degraded",
        "checks": {
            "celery": {"status": "degraded", "error": "Timeout", "duration_ms": 1001}
        }
    }
"""

import logging
import time
from typing import Any, Callable

from ninja import Router
from ninja.responses import Response

logger = logging.getLogger("ninja_boost.health")

health_router = Router(tags=["Health"], auth=None)

# ── Check registry ────────────────────────────────────────────────────────

_checks: list[dict] = []


def register_check(name: str, critical: bool = True):
    """
    Decorator: register a health check function.

    The check function should:
    - Return normally if healthy
    - Raise any exception if unhealthy

    Parameters
    ----------
    name:
        Display name for the check (shown in response JSON).
    critical:
        If True (default), failure makes the readiness probe return 503.
        If False, failure sets status to "degraded" but still returns 200.
    """
    def decorator(fn: Callable) -> Callable:
        _checks.append({"name": name, "fn": fn, "critical": critical})
        logger.debug("Health check registered: %s (critical=%s)", name, critical)
        return fn
    return decorator


def _run_check(check: dict) -> dict:
    name = check["name"]
    start = time.perf_counter()
    try:
        check["fn"]()
        duration_ms = (time.perf_counter() - start) * 1000
        return {"status": "healthy", "duration_ms": round(duration_ms, 2)}
    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        return {
            "status": "unhealthy" if check["critical"] else "degraded",
            "error":  str(exc)[:200],
            "duration_ms": round(duration_ms, 2),
        }


# ── Built-in checks ───────────────────────────────────────────────────────

def _check_database():
    from django.db import connection
    connection.ensure_connection()
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")


def _check_cache():
    from django.core.cache import cache
    key = "ninja_boost:health:ping"
    cache.set(key, "pong", timeout=5)
    val = cache.get(key)
    if val != "pong":
        raise RuntimeError("Cache write/read mismatch")


def _check_migrations():
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    executor = MigrationExecutor(connection)
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    if plan:
        unapplied = [str(m) for m, _ in plan[:5]]
        raise RuntimeError(f"Unapplied migrations: {unapplied}")


# Register built-in checks
_checks.extend([
    {"name": "database",   "fn": _check_database,   "critical": True},
    {"name": "cache",      "fn": _check_cache,       "critical": False},
    {"name": "migrations", "fn": _check_migrations,  "critical": False},
])


# ── Endpoints ─────────────────────────────────────────────────────────────

@health_router.get("/live", auth=None)
def liveness(request) -> dict:
    """
    Liveness probe — always returns 200 if the process is alive.
    Use this for Kubernetes livenessProbe.
    """
    return {"ok": True, "status": "alive"}


@health_router.get("/ready", auth=None)
def readiness(request) -> Any:
    """
    Readiness probe — runs all registered health checks.
    Returns 200 (healthy/degraded) or 503 (unhealthy).
    Use this for Kubernetes readinessProbe.
    """
    results: dict[str, dict] = {}
    overall  = "healthy"
    all_pass = True

    for check in _checks:
        result = _run_check(check)
        results[check["name"]] = result

        if result["status"] == "unhealthy":
            overall  = "unhealthy"
            all_pass = False
        elif result["status"] == "degraded" and overall == "healthy":
            overall = "degraded"

    from django.http import JsonResponse
    import json

    try:
        from ninja_boost import __version__ as _version
    except ImportError:
        _version = "unknown"

    payload = {
        "ok":      all_pass,
        "status":  overall,
        "checks":  results,
        "version": _version,
    }

    status_code = 503 if not all_pass else 200
    return JsonResponse(payload, status=status_code)


@health_router.get("/", auth=None)
def health_summary(request) -> dict:
    """Quick summary endpoint — alias for /health/live for simple uptime monitors."""
    return {"ok": True, "status": "alive"}
