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

__version__ = "0.2.0"

# ── Core ──────────────────────────────────────────────────────────────────
from ninja_boost.api import AutoAPI

# ── Async support ─────────────────────────────────────────────────────────
from ninja_boost.async_support import (
    AsyncTracingMiddleware,
    async_inject_context,
    async_paginate,
    async_rate_limit,
    async_require,
)

# ── Audit logging ─────────────────────────────────────────────────────────
from ninja_boost.audit import (
    AuditLogger,
    AuditRecord,
    AuditRouter,
    audit_log,
    audit_logger,
)
from ninja_boost.audit import (
    emit as audit_emit,
)

# ── Response caching ──────────────────────────────────────────────────────
from ninja_boost.caching import cache_manager, cache_response
from ninja_boost.dependencies import inject_context

# ── Docs ──────────────────────────────────────────────────────────────────
from ninja_boost.docs import (
    DocGuard,
    add_rate_limit_headers_to_schema,
    add_security_scheme,
    harden_docs,
)

# ── Events ────────────────────────────────────────────────────────────────
from ninja_boost.events import (
    AFTER_RESPONSE,
    BEFORE_REQUEST,
    ON_AUTH_FAILURE,
    ON_ERROR,
    ON_PERMISSION_DENIED,
    ON_PLUGIN_LOADED,
    ON_POLICY_DENIED,
    ON_RATE_LIMIT_EXCEEDED,
    ON_SERVICE_REGISTERED,
    EventBus,
    event_bus,
)
from ninja_boost.exceptions import register_exception_handlers

# ── Health checks ─────────────────────────────────────────────────────────
from ninja_boost.health import health_router, register_check

# ── Idempotency ───────────────────────────────────────────────────────────
from ninja_boost.idempotency import IdempotencyMiddleware, idempotent

# ── JWT auth ──────────────────────────────────────────────────────────────
from ninja_boost.integrations import BearerTokenAuth, JWTAuth, create_jwt_token

# ── Lifecycle ─────────────────────────────────────────────────────────────
from ninja_boost.lifecycle import LifecycleMiddleware, lifecycle_hooks

# ── Structured logging ────────────────────────────────────────────────────
from ninja_boost.logging_structured import (
    StructuredJsonFormatter,
    StructuredLoggingMiddleware,
    StructuredVerboseFormatter,
    bind_request_context,
    clear_request_context,
    get_request_context,
)

# ── Metrics ───────────────────────────────────────────────────────────────
from ninja_boost.metrics import (
    BaseMetricsBackend,
    LoggingBackend,
    Metrics,
    PrometheusBackend,
    StatsDBackend,
    metrics,
    track,
)
from ninja_boost.middleware import TracingMiddleware
from ninja_boost.pagination import auto_paginate, cursor_paginate

# ── Permissions ───────────────────────────────────────────────────────────
from ninja_boost.permissions import (
    AllowAny,
    BasePermission,
    DenyAll,
    HasPermission,
    IsAuthenticated,
    IsOwner,
    IsStaff,
    IsSuperuser,
    require,
    require_async,
)

# ── Plugins ───────────────────────────────────────────────────────────────
from ninja_boost.plugins import BoostPlugin, PluginRegistry, plugin_registry

# ── Policies ──────────────────────────────────────────────────────────────
from ninja_boost.policies import BasePolicy, PolicyRegistry, policy, policy_registry

# ── Rate limiting ─────────────────────────────────────────────────────────
from ninja_boost.rate_limiting import CacheBackend, InMemoryBackend, rate_limit
from ninja_boost.responses import wrap_response
from ninja_boost.router import AutoRouter

# ── Security headers ──────────────────────────────────────────────────────
from ninja_boost.security_headers import (
    SecurityHeadersMiddleware,
    security_report,
    with_headers,
)

# ── Services ──────────────────────────────────────────────────────────────
from ninja_boost.services import (
    BoostService,
    ServiceRegistry,
    enrich_ctx_with_services,
    inject_service,
    service_registry,
)

# ── API versioning ────────────────────────────────────────────────────────
from ninja_boost.versioning import (
    DeprecationMiddleware,
    VersionedRouter,
    deprecated,
    require_version,
    versioned_api,
)

# ── Webhook verification ──────────────────────────────────────────────────
from ninja_boost.webhook import (
    github_webhook,
    slack_webhook,
    stripe_webhook,
    verify_webhook,
)

__all__ = [
    # Core
    "AutoAPI", "AutoRouter",
    "inject_context", "register_exception_handlers",
    "TracingMiddleware", "auto_paginate", "cursor_paginate", "wrap_response",

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
    "BoostService", "ServiceRegistry", "service_registry",
    "enrich_ctx_with_services", "inject_service",

    # Metrics
    "Metrics", "metrics", "track",
    "BaseMetricsBackend", "LoggingBackend", "PrometheusBackend", "StatsDBackend",

    # Structured logging
    "StructuredJsonFormatter", "StructuredVerboseFormatter",
    "StructuredLoggingMiddleware",
    "bind_request_context", "get_request_context", "clear_request_context",

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
    "health_router", "register_check",

    # Caching
    "cache_response", "cache_manager",

    # Security headers
    "SecurityHeadersMiddleware", "with_headers", "security_report",

    # Audit
    "AuditRecord", "AuditLogger", "audit_logger",
    "audit_log", "audit_emit", "AuditRouter",

    # Versioning
    "VersionedRouter", "versioned_api",
    "require_version", "deprecated",
    "DeprecationMiddleware",

    # Idempotency
    "idempotent", "IdempotencyMiddleware",

    # Webhook verification
    "verify_webhook", "stripe_webhook", "github_webhook", "slack_webhook",

    # Auth helpers
    "BearerTokenAuth", "JWTAuth", "create_jwt_token",
]
