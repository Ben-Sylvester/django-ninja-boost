# Changelog

All notable changes to django-ninja-boost are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.2.0] — 2026-02-24

### Added

- **30 production modules** — complete automation layer for Django Ninja APIs
- `AutoAPI` / `AutoRouter` — drop-in replacements with auto-wired auth, DI, pagination, rate limiting
- `inject_context` — injects `ctx = {user, ip, trace_id, services}` into every view
- `auto_paginate` / `cursor_paginate` — transparent pagination with `?page=&size=` params
- `rate_limit` decorator — per-route and global rate limiting (`InMemoryBackend`, `CacheBackend`)
- `require` / `require_async` — declarative permissions (`IsAuthenticated`, `IsStaff`, `HasPermission`, `IsOwner`, combinators `&`, `|`, `~`)
- `BasePolicy` / `PolicyRegistry` — resource-level policy registry with `authorize()` and `@policy` decorator
- `BoostService` / `ServiceRegistry` — IoC service container with scoped and singleton services
- `EventBus` — pub/sub lifecycle events (`before_request`, `after_response`, `on_error`, …)
- `BoostPlugin` / `PluginRegistry` — plugin architecture with full lifecycle hooks
- `Metrics` — pluggable metrics (`PrometheusBackend`, `StatsDBackend`, `LoggingBackend`)
- `StructuredJsonFormatter` / `StructuredLoggingMiddleware` — JSON structured logging with request context
- `cache_response` / `CacheManager` — response caching with configurable key strategies
- `SecurityHeadersMiddleware` / `@with_headers` — HSTS, CSP, CORP, COOP, and more
- `audit_log` / `AuditRouter` / `emit` — structured audit trail with sync and async support
- `idempotent` / `IdempotencyMiddleware` — idempotency key support for POST/PATCH
- `VersionedRouter` / `versioned_api` / `@deprecated` — API versioning utilities
- `harden_docs` / `DocGuard` — docs access control with IP allowlist and staff-only mode
- `health_router` / `register_check` — Kubernetes-ready liveness and readiness probes
- `verify_webhook` / `stripe_webhook` / `github_webhook` / `slack_webhook` — HMAC webhook verification
- `async_inject_context` / `async_paginate` / `async_rate_limit` — full async view support
- `LifecycleMiddleware` — single middleware integrating all lifecycle events
- `TracingMiddleware` / `AsyncTracingMiddleware` — UUID trace ID on every request
- `JWTAuth` / `create_jwt_token` — production-ready JWT bearer auth
- `ninja-boost` CLI — `startproject`, `startapp`, `config` scaffolding commands

### Fixed

- `async_support.ensure_sync`: used `loop.run_until_complete()` inside a running event loop — replaced with `ThreadPoolExecutor` to avoid `RuntimeError`
- `audit_log`: `skip_reads` parameter was accepted but silently ignored — now correctly skips GET audit records
- `security_headers.with_headers`: per-view overrides stored on request but never read by middleware — `_apply_extra_headers()` now wires them through
- `router`: global rate limit was applied after `inject_context` — reordered so `paginate → inject_context → rate_limit → view`
- `caching`: `cache_response` stored raw Django QuerySets (not picklable) — QuerySets are now materialised to lists before `cache.set()`
- `health`: `readiness()` returned `JsonResponse` object that AutoAPI's envelope tried to re-wrap — returns plain `HttpResponse` now
- `docs`: `_patch_docs_views` fetched unbound method from `type(api)` — replaced with bound method from instance
- `webhook`: `stripe_webhook` used `dict()` to parse `Stripe-Signature` header — duplicate `v1=` keys silently dropped during key rotation; fixed with manual parsing
- `integrations`: `create_jwt_token` used deprecated `datetime.utcnow()` — replaced with `datetime.now(timezone.utc)`

---

## [0.1.0] — 2026-01-15

### Added

- Initial release: `AutoAPI`, `AutoRouter`, `inject_context`, `auto_paginate`, `rate_limit`, `TracingMiddleware`, `register_exception_handlers`, `wrap_response`
