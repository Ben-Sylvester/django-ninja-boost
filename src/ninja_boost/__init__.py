"""
ninja_boost — Zero-boilerplate automation layer for Django Ninja.

Closes the ergonomic gap with FastAPI by auto-wiring every cross-cutting
concern a production API needs.

    pip install django-ninja django-ninja-boost

Basic usage::

    from ninja_boost import AutoAPI, AutoRouter
    from ninja_boost.exceptions import register_exception_handlers

    api = AutoAPI(title="My API")
    register_exception_handlers(api)

    router = AutoRouter(tags=["Items"])

    @router.get("/", response=list[ItemOut])
    def list_items(request, ctx):
        return ItemService.list()
"""

# ── Core ──────────────────────────────────────────────────────────────────
from ninja_boost.api          import AutoAPI
from ninja_boost.router       import AutoRouter
from ninja_boost.dependencies import inject_context
from ninja_boost.exceptions   import register_exception_handlers
from ninja_boost.middleware   import TracingMiddleware
from ninja_boost.pagination   import auto_paginate
from ninja_boost.responses    import wrap_response

# ── Events ────────────────────────────────────────────────────────────────
from ninja_boost.events import (
    EventBus, event_bus,
    BEFORE_REQUEST, AFTER_RESPONSE, ON_ERROR,
    ON_AUTH_FAILURE, ON_RATE_LIMIT_EXCEEDED, ON_PERMISSION_DENIED,
    ON_POLICY_DENIED, ON_SERVICE_REGISTERED, ON_PLUGIN_LOADED,
)

# ── Plugins ───────────────────────────────────────────────────────────────
from ninja_boost.plugins import BoostPlugin, PluginRegistry, plugin_registry

# ── Rate limiting ─────────────────────────────────────────────────────────
from ninja_boost.rate_limiting import rate_limit, InMemoryBackend, CacheBackend

# ── Permissions ───────────────────────────────────────────────────────────
from ninja_boost.permissions import (
    BasePermission, require, require_async,
    IsAuthenticated, IsStaff, IsSuperuser, AllowAny, DenyAll,
    HasPermission, IsOwner,
)

# ── Policies ──────────────────────────────────────────────────────────────
from ninja_boost.policies import BasePolicy, PolicyRegistry, policy_registry, policy

# ── Services ──────────────────────────────────────────────────────────────
from ninja_boost.services import BoostService, ServiceRegistry, service_registry, inject_service

# ── Metrics ───────────────────────────────────────────────────────────────
from ninja_boost.metrics import (
    Metrics, metrics, track,
    BaseMetricsBackend, LoggingBackend, PrometheusBackend, StatsDBackend,
)

# ── Structured logging ────────────────────────────────────────────────────
from ninja_boost.logging_structured import (
    StructuredJsonFormatter, StructuredVerboseFormatter,
    StructuredLoggingMiddleware,
    bind_request_context, get_request_context,
)

# ── Async support ─────────────────────────────────────────────────────────
from ninja_boost.async_support import (
    async_inject_context, async_paginate,
    async_rate_limit, async_require,
    AsyncTracingMiddleware,
)

# ── Lifecycle ─────────────────────────────────────────────────────────────
from ninja_boost.lifecycle import LifecycleMiddleware, lifecycle_hooks

# ── Docs ──────────────────────────────────────────────────────────────────
from ninja_boost.docs import (
    DocGuard, harden_docs,
    add_security_scheme, add_rate_limit_headers_to_schema,
)

# ── Health checks ─────────────────────────────────────────────────────────
from ninja_boost.health import (
    HealthRegistry, health_registry, health_router,
    CheckStatus, Status as HealthStatus, register_builtin_checks,
)

# ── Response caching ──────────────────────────────────────────────────────
from ninja_boost.caching import cache_response, cache_invalidate, nocache

# ── Security headers ──────────────────────────────────────────────────────
from ninja_boost.security_headers import (
    SecurityHeadersMiddleware, with_headers, security_report,
)

# ── Audit logging ─────────────────────────────────────────────────────────
from ninja_boost.audit import (
    AuditRecord, AuditLogger, audit_logger,
    audit_log, emit as audit_emit, AuditRouter,
)

# ── API versioning ────────────────────────────────────────────────────────
from ninja_boost.versioning import (
    VersionRegistry, version_registry, version_router,
    versioned_api,
    min_version, max_version, only_versions, deprecated,
    AcceptHeaderVersionMiddleware, QueryStringVersionMiddleware,
)


# ── Idempotency ───────────────────────────────────────────────────────────
from ninja_boost.idempotency import idempotent, IdempotencyMiddleware

# ── Webhook verification ──────────────────────────────────────────────────
from ninja_boost.webhook import (
    verify_webhook, stripe_webhook, github_webhook, slack_webhook,
)

# ── Cursor pagination ─────────────────────────────────────────────────────
from ninja_boost.pagination import cursor_paginate

# ── JWT auth ──────────────────────────────────────────────────────────────
from ninja_boost.integrations import JWTAuth, create_jwt_token

__version__ = "0.3.0"

__all__ = [
    # Core
    "AutoAPI", "AutoRouter",
    "inject_context", "register_exception_handlers",
    "TracingMiddleware", "auto_paginate", "wrap_response",

    # Events
    "EventBus", "event_bus",
    "BEFORE_REQUEST", "AFTER_RESPONSE", "ON_ERROR",
    "ON_AUTH_FAILURE", "ON_RATE_LIMIT_EXCEEDED", "ON_PERMISSION_DENIED",
    "ON_POLICY_DENIED", "ON_SERVICE_REGISTERED", "ON_PLUGIN_LOADED",

    # Plugins
    "BoostPlugin", "PluginRegistry", "plugin_registry",

    # Rate limiting
    "rate_limit", "InMemoryBackend", "CacheBackend",

    # Permissions
    "BasePermission", "require", "require_async",
    "IsAuthenticated", "IsStaff", "IsSuperuser", "AllowAny", "DenyAll",
    "HasPermission", "IsOwner",

    # Policies
    "BasePolicy", "PolicyRegistry", "policy_registry", "policy",

    # Services
    "BoostService", "ServiceRegistry", "service_registry", "inject_service",

    # Metrics
    "Metrics", "metrics", "track",
    "BaseMetricsBackend", "LoggingBackend", "PrometheusBackend", "StatsDBackend",

    # Structured logging
    "StructuredJsonFormatter", "StructuredVerboseFormatter",
    "StructuredLoggingMiddleware",
    "bind_request_context", "get_request_context",

    # Async support
    "async_inject_context", "async_paginate",
    "async_rate_limit", "async_require",
    "AsyncTracingMiddleware",

    # Lifecycle
    "LifecycleMiddleware", "lifecycle_hooks",

    # Docs
    "DocGuard", "harden_docs",
    "add_security_scheme", "add_rate_limit_headers_to_schema",

    # Health
    "HealthRegistry", "health_registry", "health_router",
    "CheckStatus", "HealthStatus", "register_builtin_checks",

    # Caching
    "cache_response", "cache_invalidate", "nocache",

    # Security headers
    "SecurityHeadersMiddleware", "with_headers", "security_report",

    # Audit
    "AuditRecord", "AuditLogger", "audit_logger",
    "audit_log", "audit_emit", "AuditRouter",

    # Versioning
    "VersionRegistry", "version_registry", "version_router",
    "versioned_api",
    "min_version", "max_version", "only_versions", "deprecated",
    "AcceptHeaderVersionMiddleware", "QueryStringVersionMiddleware",

    # Idempotency
    "idempotent", "IdempotencyMiddleware",

    # Webhook verification
    "verify_webhook", "stripe_webhook", "github_webhook", "slack_webhook",

    # Cursor pagination
    "cursor_paginate",

    # JWT auth
    "JWTAuth", "create_jwt_token",
]

# ── Bonus modules (from extended feature set) ─────────────────────────────
from ninja_boost.audit import (
    AuditRouter, audit_log,
)
from ninja_boost.idempotency import idempotent
from ninja_boost.security_headers import SecurityHeadersMiddleware
from ninja_boost.webhook import (
    verify_webhook, stripe_webhook, github_webhook, slack_webhook,
)
from ninja_boost.health import health_router, register_check
from ninja_boost.caching import cache_response, cache_manager
from ninja_boost.versioning import (
    VersionedRouter, versioned_api, deprecated, require_version,
    DeprecationMiddleware,
)

__all__ += [
    # Audit
    "AuditRouter", "audit_log",
    # Idempotency
    "idempotent",
    # Security
    "SecurityHeadersMiddleware",
    # Webhooks
    "verify_webhook", "stripe_webhook", "github_webhook", "slack_webhook",
    # Health
    "health_router", "register_check",
    # Caching
    "cache_response", "cache_manager",
    # Versioning
    "VersionedRouter", "versioned_api", "deprecated", "require_version",
    "DeprecationMiddleware",
]
