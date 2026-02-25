# django-ninja-boost

**The production automation layer Django Ninja was always missing.**

Auto-wires everything a real API needs — auth, envelopes, pagination, DI, rate limiting, permissions, policies, services, events, async, structured logging, metrics, health checks, caching, versioning, idempotency, webhook verification, security headers, audit logging, and docs hardening — configure once, build forever.

[![PyPI version](https://img.shields.io/pypi/v/django-ninja-boost.svg)](https://pypi.org/project/django-ninja-boost/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Django 4.2+](https://img.shields.io/badge/django-4.2+-green.svg)](https://djangoproject.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://github.com/bensylvenus/django-ninja-boost/actions/workflows/test.yml/badge.svg)](https://github.com/bensylvenus/django-ninja-boost/actions)

---

## Table of Contents

- [What is this?](#what-is-this)
- [Why "Boost" and not "Auto"?](#why-boost-and-not-auto)
- [The problem it solves](#the-problem-it-solves)
- [Feature overview](#feature-overview)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Adding to an existing project](#adding-to-an-existing-project)
- [Feature reference](#feature-reference)
  - [AutoAPI](#autoapi)
  - [AutoRouter](#autorouter)
  - [Context injection](#context-injection)
  - [Auto-pagination (offset)](#auto-pagination-offset)
  - [Cursor-based pagination](#cursor-based-pagination)
  - [TracingMiddleware](#tracingmiddleware)
  - [Exception handlers](#exception-handlers)
  - [Event bus](#event-bus)
  - [Plugin system](#plugin-system)
  - [Rate limiting](#rate-limiting)
  - [Declarative permissions](#declarative-permissions)
  - [Policy registry](#policy-registry)
  - [Service registry](#service-registry)
  - [Structured logging](#structured-logging)
  - [Metrics hooks](#metrics-hooks)
  - [Async support](#async-support)
  - [Lifecycle middleware](#lifecycle-middleware)
  - [Health checks](#health-checks)
  - [Response caching](#response-caching)
  - [API versioning](#api-versioning)
  - [Docs hardening](#docs-hardening)
  - [Idempotency](#idempotency)
  - [Webhook verification](#webhook-verification)
  - [Security headers](#security-headers)
  - [Audit logging](#audit-logging)
  - [JWT auth](#jwt-auth)
- [Configuration reference](#configuration-reference)
- [Custom integrations](#custom-integrations)
- [Real-world patterns](#real-world-patterns)
- [Testing](#testing)
- [Deployment](#deployment)
- [Publishing to PyPI](#publishing-to-pypi)
- [CLI reference](#cli-reference)
- [Security considerations](#security-considerations)
- [Performance notes](#performance-notes)
- [Troubleshooting & FAQ](#troubleshooting--faq)
- [Comparison table](#comparison-table)
- [Changelog](#changelog)
- [Contributing](#contributing)
- [License](#license)

---

## What is this?

**django-ninja-boost** is a zero-configuration automation layer that sits on top of [Django Ninja](https://django-ninja.dev/) and eliminates every piece of repetitive boilerplate a production API team writes.

It does **not** replace Django Ninja — it extends it. Every argument `NinjaAPI` and `Router` accept still works. You can migrate one router at a time.

```python
# Before: repeated ceremony on every single router
from ninja import NinjaAPI, Router
from ninja.security import HttpBearer

class JWTAuth(HttpBearer):
    def authenticate(self, request, token): ...   # copy-pasted everywhere

router = Router()

@router.get("/users", auth=JWTAuth())
def list_users(request):
    page  = int(request.GET.get("page", 1))       # manual pagination
    size  = int(request.GET.get("size", 20))       # every. single. time.
    qs    = User.objects.all()
    total = qs.count()
    items = list(qs[(page-1)*size : page*size])
    return {"ok": True, "data": {"items": items, "total": total}}

# After: one import, everything auto-wired
from ninja_boost import AutoAPI, AutoRouter

api    = AutoAPI()
router = AutoRouter(tags=["Users"])

@router.get("/users", response=list[UserOut])
def list_users(request, ctx):
    return User.objects.all()   # paginated, enveloped, and auth-gated automatically
```

---

## Why "Boost" and not "Auto"?

| Name | Problem |
|------|---------|
| `django-ninja-auto` | "Auto" implies magic you can't control; sounds like it replaces your architecture. |
| `django-ninja-boost` | Honest: it makes your existing Django Ninja code faster and more powerful. You add rocket fuel — you still steer the rocket. |
| `django-ninja-plus` | Generic — every "plus" package sounds the same in search results. |
| `django-ninja-ext` | Sounds like an afterthought extension, not a first-class layer. |
| `django-ninja-kit` | A "kit" implies manual assembly; Boost is pre-assembled. |

**Verdict:** `django-ninja-boost` wins — memorable, honest, differentiates well in `pip search ninja` results.

---

## The problem it solves

Every Django Ninja project rewrites the same 8 things before writing a single line of business logic:

1. **Auth** — copy-pasting an `HttpBearer` subclass
2. **Response envelope** — manually wrapping every return value
3. **Pagination** — writing `page`/`size` extraction code on every list endpoint
4. **Tracing** — attaching a trace ID to requests for log correlation
5. **Error handling** — registering exception handlers consistently
6. **Context injection** — passing `user`, `ip`, `trace_id` into every view
7. **Rate limiting** — rolling your own or depending on poorly maintained packages
8. **Permissions** — writing `if not user.is_staff: raise HttpError(403, ...)` everywhere

After that first wave, the second wave arrives:
- Prometheus metrics on every endpoint
- Structured JSON logging so logs are actually searchable
- OpenAPI docs secured in production
- Kubernetes health probes
- Idempotency keys so retried payments don't double-charge
- Webhook signature verification for Stripe, GitHub, Slack
- Audit trails for compliance
- API versioning

ninja_boost wires every one of these — once, correctly, with tests — so you write them exactly zero times.

---

## Feature overview

| Feature | Module | What it does |
|---------|--------|-------------|
| AutoAPI | `api.py` | NinjaAPI subclass — auto-wires auth + response envelope |
| AutoRouter | `router.py` | Router subclass — auto-wires DI, pagination, async detection |
| Offset pagination | `pagination.py` | `?page=&size=` with `COUNT(*)` + `LIMIT/OFFSET` |
| Cursor pagination | `pagination.py` | `@cursor_paginate` — O(1) keyset pagination for large tables |
| DI injection | `dependencies.py` | `ctx = {user, ip, trace_id, services}` in every view |
| Tracing | `middleware.py` | UUID `X-Trace-Id` on every request/response |
| Exception handlers | `exceptions.py` | Consistent `{"ok": false, ...}` error shapes |
| Event bus | `events.py` | `@event_bus.on("before_request")` — pub/sub lifecycle system |
| Plugin system | `plugins.py` | `BoostPlugin` hooks — extend without forking |
| Rate limiting | `rate_limiting.py` | `@rate_limit("30/minute")` — memory + Redis backends |
| Permissions | `permissions.py` | `@require(IsStaff)`, composable with `&`, `\|`, `~` |
| Policies | `policies.py` | Resource-level `BasePolicy` classes + central registry |
| Service registry | `services.py` | IoC container, `ctx["services"]["name"]` injection |
| Structured logging | `logging_structured.py` | JSON logs with trace_id/user_id auto-context |
| Metrics | `metrics.py` | Prometheus, StatsD, Datadog, logging adapters |
| Async support | `async_support.py` | Native async views — auto-detected, auto-wrapped |
| Lifecycle middleware | `lifecycle.py` | Unified before/after/error orchestration |
| Health checks | `health.py` | Kubernetes-ready `/health/live` and `/health/ready` |
| Response caching | `caching.py` | `@cache_response(ttl=60)` with invalidation |
| API versioning | `versioning.py` | URL, header, and query-string versioning strategies |
| Docs hardening | `docs.py` | IP allowlist, staff-only, disable-in-production for `/docs` |
| Idempotency | `idempotency.py` | `@idempotent(ttl="24h")` — safe payment/order retries |
| Webhook verification | `webhook.py` | Stripe, GitHub, Slack, and generic HMAC verification |
| Security headers | `security_headers.py` | HSTS, CSP, X-Frame-Options auto-set |
| Audit logging | `audit.py` | Who did what to which resource and when |
| JWT auth | `integrations.py` | `JWTAuth` + `create_jwt_token()` — production-ready |
| Scaffolding CLI | `cli.py` | `ninja-boost startproject` / `startapp` / `config` |

---

## Installation

**Core only (no optional dependencies):**
```bash
pip install django-ninja-boost
```

**With optional backends:**
```bash
pip install "django-ninja-boost[prometheus]"   # Prometheus metrics
pip install "django-ninja-boost[statsd]"       # StatsD/Datadog metrics
pip install "django-ninja-boost[redis]"        # Redis rate limiting + caching
pip install "django-ninja-boost[all]"          # all backends
```

**With JWT (recommended for production):**
```bash
pip install "django-ninja-boost" PyJWT
```

**Add to settings.py:**
```python
INSTALLED_APPS = [
    ...
    "ninja_boost",
]

MIDDLEWARE = [
    ...
    "ninja_boost.middleware.TracingMiddleware",
    # Optional: full lifecycle (replaces TracingMiddleware alone for production)
    # "ninja_boost.lifecycle.LifecycleMiddleware",
]
```

---

## Quick Start

### Option A — Scaffold a new project

```bash
pip install django-ninja-boost
ninja-boost startproject myapi
cd myapi
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

### Option B — Manual setup

**urls.py:**
```python
from ninja_boost import AutoAPI
from ninja_boost.exceptions import register_exception_handlers

api = AutoAPI(title="My API", version="1.0")
register_exception_handlers(api)

urlpatterns = [path("api/", api.urls)]
```

**routers.py:**
```python
from ninja_boost import AutoRouter

router = AutoRouter(tags=["Items"])

@router.get("/", response=list[ItemOut])
def list_items(request, ctx):
    return Item.objects.filter(active=True)
```

**Test it:**
```bash
curl -H "Authorization: Bearer demo" http://localhost:8000/api/items/?size=5
# {"ok": true, "data": {"items": [...], "page": 1, "size": 5, "total": 42, "pages": 9}}
```

---

## Adding to an existing project

Replace one router at a time:
```python
from ninja_boost import AutoRouter       # swap from ninja import Router
router = AutoRouter(tags=["NewFeature"])
```

Both old `Router` and new `AutoRouter` instances can be registered on the same `api`. No breaking changes.

---

## Feature reference

### AutoAPI

`AutoAPI` is a drop-in `NinjaAPI` subclass:

```python
api = AutoAPI(title="Bookstore API", version="2.0", urls_namespace="api")
```

Automatically adds: default auth from settings, response envelope, double-wrap prevention, plugin startup hooks, docs hardening.

**Override auth per-route:**
```python
@router.get("/public", auth=None)       # no auth on this route
@router.get("/special", auth=ApiKey())  # different auth scheme
```

---

### AutoRouter

Automatically applies auth, DI, and pagination:

```python
router = AutoRouter(tags=["Users"])

# Opt out of specific features per-route:
@router.get("/health", auth=None, inject=False, paginate=False)
def health(request):
    return {"status": "ok"}

@router.post("/", response=UserOut, paginate=False)
def create_user(request, ctx, payload: UserCreate):
    return UserService.create(payload)
```

---

### Context injection

Every AutoRouter view receives `ctx` as its second argument:

```python
@router.get("/me")
def me(request, ctx):
    print(ctx["user"])      # → {"user_id": 42, "is_staff": False}
    print(ctx["ip"])        # → "203.0.113.1"
    print(ctx["trace_id"])  # → "a1b2c3d4e5f6..."
    print(ctx["services"])  # → {"orders": <OrderService>}
```

---

### Auto-pagination (offset)

Transparent pagination on any list endpoint:

```python
@router.get("/items", response=list[ItemOut])
def list_items(request, ctx):
    return Item.objects.filter(active=True)   # QuerySet returned raw
    # Automatically becomes:
    # {"items": [...], "page": 1, "size": 20, "total": 142, "pages": 8}
```

Query params: `?page=2&size=50`

---

### Cursor-based pagination

For large tables where `OFFSET` is slow:

```python
from ninja_boost import cursor_paginate

@router.get("/feed", paginate=False)
@cursor_paginate(field="created_at", order="desc")
def get_feed(request, ctx):
    return Post.objects.order_by("-created_at")
```

Response:
```json
{"items": [...], "next_cursor": "eyJpZCI6IDQyfQ", "prev_cursor": null,
 "size": 20, "has_next": true, "has_prev": false}
```

Pass `?cursor=<next_cursor>` to get the next page. O(1) regardless of dataset size.

| | Offset | Cursor |
|-|--------|--------|
| Speed on large tables | O(offset) — degrades | O(1) — always fast |
| Stable under writes | No — duplicates possible | Yes |
| Jump to arbitrary page | Yes | No |
| Total count | Yes | No |

---

### TracingMiddleware

Stamps every request with a UUID trace ID:

```python
MIDDLEWARE = [..., "ninja_boost.middleware.TracingMiddleware"]
```

- `request.trace_id` in views
- `ctx["trace_id"]` in AutoRouter views  
- `X-Trace-Id` response header for clients and APM tools

---

### Exception handlers

Consistent error envelopes:

```python
api = AutoAPI()
register_exception_handlers(api)

# Error shape: {"ok": false, "error": "Not found.", "code": 404}
# Fires on_error event for Sentry/alerting plugins
```

---

### Event bus

Pub/sub lifecycle system:

```python
from ninja_boost.events import event_bus

@event_bus.on("before_request")
def log_request(request, ctx, **kw):
    logger.info("→ %s %s [%s]", request.method, request.path, ctx["trace_id"])

@event_bus.on("after_response")
def record_timing(request, ctx, response, duration_ms, **kw):
    logger.info("← %d %.1fms", response.status_code, duration_ms)

@event_bus.on("on_error")
def alert(request, ctx, exc, **kw):
    Sentry.capture_exception(exc)
```

| Event | When |
|-------|------|
| `BEFORE_REQUEST` | Before every view |
| `AFTER_RESPONSE` | After every response |
| `ON_ERROR` | Unhandled exception |
| `ON_AUTH_FAILURE` | Auth returns None |
| `ON_RATE_LIMIT_EXCEEDED` | Rate limit hit |
| `ON_PERMISSION_DENIED` | `@require` fails |
| `ON_POLICY_DENIED` | Policy check fails |
| `ON_SERVICE_REGISTERED` | Service registered |
| `ON_PLUGIN_LOADED` | Plugin loaded |

Supports both sync and async handlers. Handler exceptions are isolated — they never crash the request cycle.

---

### Plugin system

Package cross-cutting concerns as reusable units:

```python
from ninja_boost.plugins import BoostPlugin, plugin_registry

class SentryPlugin(BoostPlugin):
    name = "sentry"

    def on_startup(self, api):
        sentry_sdk.init(dsn=settings.SENTRY_DSN)

    def on_error(self, request, exc, ctx, **kw):
        sentry_sdk.capture_exception(exc)

    def on_auth_failure(self, request, **kw):
        security_logger.warning("Auth failure: %s", request.META["REMOTE_ADDR"])

plugin_registry.register(SentryPlugin())
```

Available hooks: `on_startup`, `on_request`, `on_response`, `on_error`, `on_auth_failure`, `on_rate_limit_exceeded`, `on_permission_denied`.

Auto-load from settings:
```python
NINJA_BOOST = {
    "PLUGINS": ["myproject.plugins.SentryPlugin", "myproject.plugins.DatadogPlugin"],
}
```

---

### Rate limiting

```python
from ninja_boost import rate_limit

@router.get("/search")
@rate_limit("30/minute")                        # by client IP

@router.post("/login", auth=None, paginate=False)
@rate_limit("5/minute", key="ip")               # explicit IP

@router.post("/send-email")
@rate_limit("10/hour", key="user")              # by authenticated user

@router.get("/reports")
@rate_limit("100/day", key=lambda req, ctx: f"tenant:{ctx['tenant_id']}")  # custom key
```

Rate string format: `"N/second"`, `"N/minute"`, `"N/hour"`, `"N/day"`.

**Backends:**
```python
# In-memory (default) — single process, zero dependencies
# Redis — multi-process, requires django-redis
NINJA_BOOST = {"RATE_LIMIT": {
    "BACKEND": "ninja_boost.rate_limiting.CacheBackend",
    "DEFAULT": "200/minute",   # global default for all routes
}}
```

Response headers set automatically: `X-RateLimit-Limit`, `X-RateLimit-Remaining`.

---

### Declarative permissions

```python
from ninja_boost import require, IsAuthenticated, IsStaff, HasPermission, IsOwner

@router.get("/admin/users")
@require(IsStaff)
def admin_users(request, ctx): ...

@router.delete("/{id}")
@require(IsAuthenticated & IsOwner(
    lambda req, ctx, id, **kw: Order.objects.get(id=id).user_id
))
def delete_order(request, ctx, id: int): ...

@router.post("/reports")
@require(IsAuthenticated & HasPermission("analytics.view_report"))
def reports(request, ctx, payload): ...
```

Built-in permissions: `IsAuthenticated`, `IsStaff`, `IsSuperuser`, `AllowAny`, `DenyAll`, `HasPermission(codename)`, `IsOwner(fn)`.

Compose with operators: `IsStaff | IsOwner(...)`, `~HasPermission("app.banned")`.

**Custom permission:**
```python
from ninja_boost.permissions import BasePermission

class IsPremiumUser(BasePermission):
    def has_permission(self, request, ctx) -> bool:
        return Subscription.objects.filter(
            user_id=(ctx.get("user") or {}).get("user_id"), active=True
        ).exists()
```

---

### Policy registry

Centralise resource access rules:

```python
from ninja_boost.policies import BasePolicy, policy_registry, policy

class OrderPolicy(BasePolicy):
    resource_name = "order"

    def before(self, request, ctx, action, obj=None):
        if (ctx.get("user") or {}).get("is_superuser"):
            return True   # superusers bypass all checks

    def view(self, request, ctx, obj=None) -> bool:
        return obj is None or str(obj.user_id) == str((ctx.get("user") or {}).get("user_id"))

    def update(self, request, ctx, obj=None) -> bool:
        return obj is not None and str(obj.user_id) == str((ctx.get("user") or {}).get("user_id"))

    def delete(self, request, ctx, obj=None) -> bool:
        return (ctx.get("user") or {}).get("is_staff", False)

policy_registry.register(OrderPolicy())

# Imperative check in view:
policy_registry.authorize(request, ctx, "order", "update", obj=order)

# Decorator style:
@router.delete("/{id}")
@policy("order", "delete", get_obj=lambda id, **kw: get_object_or_404(Order, id=id))
def delete_order(request, ctx, id: int): ...
```

Auto-load from settings: `NINJA_BOOST = {"POLICIES": ["apps.orders.policies.OrderPolicy"]}`.

---

### Service registry

IoC container for dependency injection:

```python
from ninja_boost.services import BoostService, service_registry

class EmailService(BoostService):
    name = "email"
    def send(self, to, subject, body): ...

service_registry.register(EmailService())

# In views:
@router.post("/register")
def register(request, ctx, payload: RegisterPayload):
    user = UserService.create(payload)
    ctx["services"]["email"].send(user.email, "Welcome!", "...")
    return user

# Or with decorator:
from ninja_boost import inject_service

@router.post("/checkout")
@inject_service("orders", "email", "payments")
def checkout(request, ctx, payload):
    order = ctx["svc_orders"].create(payload)
    ctx["svc_payments"].charge(payload.card_token, order.total)
    ctx["svc_email"].send(ctx["user"]["email"], "Order confirmed", "...")
    return order
```

**Scoped services** (`scoped = True`) create a fresh instance per request — useful for request-local caches or database transactions.

---

### Structured logging

JSON logs with automatic request context:

```python
# settings.py
LOGGING = {
    "version": 1,
    "formatters": {
        "json":    {"()": "ninja_boost.logging_structured.StructuredJsonFormatter"},
        "verbose": {"()": "ninja_boost.logging_structured.StructuredVerboseFormatter"},  # for dev
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json"}},
    "root":     {"handlers": ["console"], "level": "INFO"},
}
```

Every log record during a request automatically carries `trace_id`, `method`, `path`, `user_id`, `ip`:

```json
{"timestamp": "2026-02-24T10:30:00.123Z", "level": "INFO",
 "logger": "apps.orders", "message": "Order created",
 "trace_id": "a1b2c3d4...", "method": "POST", "path": "/api/orders/",
 "user_id": 42, "ip": "203.0.113.1", "order_id": 7}
```

Context is bound via `contextvars` — async-safe, no threadlocal hacks.

---

### Metrics hooks

```python
# settings.py
NINJA_BOOST = {
    "METRICS": {
        "BACKEND":   "ninja_boost.metrics.PrometheusBackend",
        "NAMESPACE": "myapi",
    },
}
```

**Auto-tracked:** `request_total`, `request_duration_ms`, `request_errors_total`, `active_requests`.

**Custom metrics:**
```python
from ninja_boost import metrics

metrics.increment("orders_created", labels={"tier": "premium"})
metrics.timing("checkout_duration_ms", result.duration_ms)

@router.get("/slow")
@track("slow_query")    # auto-records call count + duration
def slow(request, ctx): ...
```

**Backends:** `LoggingBackend` (zero deps), `PrometheusBackend`, `StatsDBackend`, or subclass `BaseMetricsBackend`.

---

### Async support

Write async views — everything works automatically:

```python
@router.get("/items")
async def list_items(request, ctx):
    items = [i async for i in Item.objects.filter(active=True).aiterator()]
    return items   # still auto-paginated

@router.post("/process")
async def process(request, ctx, payload: ProcessPayload):
    result = await external_api.call(payload.data)
    return result
```

`AutoRouter` detects async views and applies `async_inject_context`, `async_paginate`, and `async_rate_limit` automatically. No configuration needed.

**ASGI deployment:**
```bash
uvicorn myproject.asgi:application --workers 4 --loop uvloop
```

---

### Lifecycle middleware

Single middleware that orchestrates all cross-cutting concerns:

```python
MIDDLEWARE = [
    "ninja_boost.middleware.TracingMiddleware",
    "ninja_boost.lifecycle.LifecycleMiddleware",
]
```

Order per request: bind log context → increment active_requests gauge → fire `before_request` → execute view → set rate limit headers → update metrics → fire `after_response` → write access log → decrement gauge. On error: fire `on_error`, increment error counter, re-raise.

---

### Health checks

Kubernetes-ready liveness and readiness probes:

```python
from ninja_boost.health import health_router, register_check

# Built-in checks (database, cache, migrations) are auto-registered on import.
# Add your own:
@register_check("redis", critical=True)
def check_redis():
    from django.core.cache import cache
    cache.set("__health__", 1, timeout=5)
    assert cache.get("__health__") == 1

api.add_router("/health", health_router)
```

Endpoints: `GET /health/live` (always 200), `GET /health/ready` (503 if critical check fails), `GET /health/` (full status).

```yaml
# kubernetes
livenessProbe:
  httpGet: {path: /api/health/live, port: 8000}
readinessProbe:
  httpGet: {path: /api/health/ready, port: 8000}
```

---

### Response caching

```python
from ninja_boost import cache_response
from ninja_boost.caching import cache_manager

@router.get("/products")
@cache_response(ttl=300, key="user")        # 5 min, per authenticated user
def list_products(request, ctx): ...

@router.get("/public/stats")
@cache_response(ttl=3600)                   # 1 hour, shared
def public_stats(request, ctx): ...

@router.post("/products")
def create_product(request, ctx, payload):
    product = ProductService.create(payload)
    # Bust a specific cached entry by its raw key:
    cache_manager.invalidate_key("myapp.views.list_products:/api/products:")
    # Or bust everything matching a pattern (requires django-redis):
    cache_manager.invalidate_prefix("/api/products")
    return product
```

---

### API versioning

```python
from ninja_boost.versioning import versioned_api, require_version, deprecated

# Build one AutoAPI per version:
apis = versioned_api(["v1", "v2"], title="My API")

# In urls.py:
# urlpatterns = [path(f"api/{v}/", api.urls) for v, api in apis.items()]

# Header-based version enforcement per route:
@router.get("/items")
@require_version("2.0", header="X-API-Version")
def list_items_v2(request, ctx): ...

@router.get("/items/legacy")
@deprecated(sunset="2026-12-01", replacement="/api/v2/items/")
def list_items_v1(request, ctx): ...   # adds Deprecation response header

# Deprecation headers middleware:
MIDDLEWARE = [..., "ninja_boost.versioning.DeprecationMiddleware"]
```

---

### Docs hardening

```python
# settings.py
NINJA_BOOST = {
    "DOCS": {
        "DISABLE_IN_PRODUCTION": True,
        "REQUIRE_STAFF":         False,
        "ALLOWED_IPS":           ["127.0.0.1", "10.0.0.0/8"],
    },
}

# Or programmatically:
from ninja_boost.docs import harden_docs, add_security_scheme

harden_docs(api)
add_security_scheme(api, "BearerAuth", bearer_format="JWT")
```

---

### Idempotency

Safe retries for mutations — essential for payment APIs:

```python
from ninja_boost import idempotent

@router.post("/payments")
@idempotent(ttl="24h")
def charge_card(request, ctx, payload: ChargePayload):
    return PaymentService.charge(payload)   # executes exactly once per key
```

Client sends `X-Idempotency-Key: <uuid>`. Retries with the same key return the cached result without re-executing the view. Replay is detectable via `X-Idempotency-Replay: true` response header.

Concurrent requests with the same key receive HTTP 409 while the first request is in-flight.

---

### Webhook verification

```python
from ninja_boost import stripe_webhook, github_webhook, slack_webhook, verify_webhook

@router.post("/webhooks/stripe", auth=None, paginate=False)
@stripe_webhook()    # reads STRIPE_WEBHOOK_SECRET env var
def handle_stripe(request, ctx):
    event = json.loads(request.body)
    if event["type"] == "payment_intent.succeeded":
        PaymentService.fulfill(event["data"]["object"]["id"])

@router.post("/webhooks/github", auth=None, paginate=False)
@github_webhook()    # reads GITHUB_WEBHOOK_SECRET env var
def handle_github(request, ctx):
    payload = json.loads(request.body)
    DeployService.trigger(payload["repository"]["full_name"])

@router.post("/webhooks/slack", auth=None, paginate=False)
@slack_webhook()     # reads SLACK_SIGNING_SECRET env var
def handle_slack(request, ctx): ...

# Generic HMAC-SHA256:
@verify_webhook(secret_env="MY_WEBHOOK_SECRET", header="X-Signature")
```

All verifiers use `hmac.compare_digest` to prevent timing attacks. Stripe and Slack also validate timestamps to reject replayed webhooks within a 5-minute window.

---

### Security headers

```python
MIDDLEWARE = [..., "ninja_boost.security_headers.SecurityHeadersMiddleware"]
```

Sets by default: `Strict-Transport-Security`, `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, `Content-Security-Policy`.

```python
NINJA_BOOST = {
    "SECURITY_HEADERS": {
        "HSTS_MAX_AGE": 63072000,          # 2 years
        "HSTS_PRELOAD": True,
        "CSP": "default-src 'self'; script-src 'self' cdn.example.com",
        "SKIP_PATHS": ["/api/webhooks/"],  # exclude webhook endpoints
    },
}
```

Per-route override:
```python
from ninja_boost import with_headers

@router.get("/embed")
@with_headers({"X-Frame-Options": "ALLOWALL"})
def embeddable_widget(request, ctx): ...
```

---

### Audit logging

Tamper-evident record of every sensitive action:

```python
from ninja_boost import audit_log, AuditRouter

@router.put("/{id}")
@audit_log(action="order.update", resource="order", resource_id=lambda id, **kw: id)
def update_order(request, ctx, id: int, payload): ...

# Auto-audit all routes on a router:
admin_router = AuditRouter(tags=["Admin"])
```

Audit record:
```json
{"timestamp": "...", "actor_id": 42, "action": "order.update",
 "resource": "order", "resource_id": "7", "outcome": "success",
 "ip": "203.0.113.1", "trace_id": "a1b2c3d4..."}
```

Backends: `LoggingBackend` (default), `DatabaseBackend` (stores in DB), `MultiBackend` (fan-out).

---

### JWT auth

Replace the demo `BearerTokenAuth` for production:

```python
# settings.py
NINJA_BOOST = {"AUTH": "ninja_boost.integrations.JWTAuth", ...}

JWT_SECRET_KEY  = env("JWT_SECRET_KEY")
JWT_ALGORITHM   = "HS256"
JWT_EXPIRY_MINS = 60
```

**Issue tokens:**
```python
from ninja_boost.integrations import create_jwt_token

@router.post("/auth/login", auth=None, paginate=False)
def login(request, ctx, payload: LoginPayload):
    user = authenticate(username=payload.username, password=payload.password)
    if user is None:
        raise HttpError(401, "Invalid credentials.")
    token = create_jwt_token({"user_id": user.id, "is_staff": user.is_staff})
    return {"access_token": token, "token_type": "bearer"}
```

Decoded payload becomes `ctx["user"]` in every view.

---

## Configuration reference

```python
NINJA_BOOST = {
    # Core (dotted-path strings)
    "AUTH":             "ninja_boost.integrations.JWTAuth",
    "RESPONSE_WRAPPER": "ninja_boost.responses.wrap_response",
    "PAGINATION":       "ninja_boost.pagination.auto_paginate",
    "DI":               "ninja_boost.dependencies.inject_context",

    # Rate limiting
    "RATE_LIMIT": {
        "DEFAULT":  None,              # e.g. "200/minute"
        "BACKEND":  "ninja_boost.rate_limiting.InMemoryBackend",
    },

    # Metrics
    "METRICS": {
        "BACKEND":    None,            # e.g. "ninja_boost.metrics.PrometheusBackend"
        "NAMESPACE":  "ninja_boost",
    },

    # Docs
    "DOCS": {
        "ENABLED":                True,
        "REQUIRE_STAFF":          False,
        "REQUIRE_AUTH":           False,
        "ALLOWED_IPS":            [],
        "DISABLE_IN_PRODUCTION":  False,
        "TITLE":                  None,
        "DESCRIPTION":            None,
        "VERSION":                None,
        "SERVERS":                [],
    },

    # Auto-loaded on startup
    "PLUGINS":   ["myproject.plugins.SentryPlugin"],
    "POLICIES":  ["apps.orders.policies.OrderPolicy"],
    "SERVICES":  ["apps.users.services.UserService"],

    # Idempotency
    "IDEMPOTENCY": {
        "HEADER":   "X-Idempotency-Key",
        "TTL":      86400,
        "BACKEND":  "default",
    },

    # Security headers
    "SECURITY_HEADERS": {
        "HSTS_MAX_AGE":            31536000,
        "HSTS_INCLUDE_SUBDOMAINS": True,
        "HSTS_PRELOAD":            False,
        "FRAME_OPTIONS":           "DENY",
        "SKIP_PATHS":              [],
    },
}
```

---

## Custom integrations

### Custom auth (JWT with RS256)

```python
from ninja.security import HttpBearer
import jwt

class RS256Auth(HttpBearer):
    def authenticate(self, request, token: str):
        with open(settings.JWT_PUBLIC_KEY_PATH) as f:
            public_key = f.read()
        try:
            return jwt.decode(token, public_key, algorithms=["RS256"])
        except jwt.InvalidTokenError:
            return None

NINJA_BOOST = {"AUTH": "myproject.auth.RS256Auth", ...}
```

### Django session auth

```python
from ninja.security import django_auth

class SessionAuth:
    def __call__(self): return django_auth

NINJA_BOOST = {"AUTH": "myproject.auth.SessionAuth", ...}
```

### Custom response envelope

```python
def jsonapi_envelope(data):
    return {"data": data, "meta": {"version": "1.0"}, "links": {}}

NINJA_BOOST = {"RESPONSE_WRAPPER": "myproject.responses.jsonapi_envelope", ...}
```

### Custom DI context (add tenant)

```python
from functools import wraps
from ninja_boost.dependencies import _client_ip

def tenant_inject(func):
    @wraps(func)
    def wrapper(request, *args, **kwargs):
        user   = getattr(request, "auth", None)
        tenant = Tenant.objects.filter(user_id=(user or {}).get("user_id")).first()
        ctx = {
            "user":      user,
            "ip":        _client_ip(request),
            "trace_id":  getattr(request, "trace_id", None),
            "tenant":    tenant,
            "tenant_id": tenant.id if tenant else None,
        }
        return func(request, ctx, *args, **kwargs)
    return wrapper

NINJA_BOOST = {"DI": "myproject.di.tenant_inject", ...}
```

---

## Real-world patterns

### Production urls.py

```python
from django.contrib import admin
from django.urls import path
from ninja_boost import AutoAPI
from ninja_boost.exceptions import register_exception_handlers
from ninja_boost.docs import add_security_scheme, add_rate_limit_headers_to_schema
from ninja_boost.health import health_router

api = AutoAPI(title="Acme API", version="2.0")
register_exception_handlers(api)
add_security_scheme(api, "BearerAuth", bearer_format="JWT")
add_rate_limit_headers_to_schema(api)

from apps.auth.routers   import router as auth_router
from apps.users.routers  import router as users_router
from apps.orders.routers import router as orders_router

api.add_router("/auth",   auth_router)
api.add_router("/users",  users_router)
api.add_router("/orders", orders_router)
api.add_router("/health", health_router)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/",   api.urls),
]
```

### Sentry plugin

```python
from ninja_boost.plugins import BoostPlugin

class SentryPlugin(BoostPlugin):
    name = "sentry"

    def on_startup(self, api):
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration
        sentry_sdk.init(dsn=settings.SENTRY_DSN, integrations=[DjangoIntegration()])

    def on_error(self, request, exc, ctx, **kw):
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            scope.set_tag("trace_id", ctx.get("trace_id"))
            scope.set_user({"id": (ctx.get("user") or {}).get("user_id")})
            sentry_sdk.capture_exception(exc)
```

### Multi-tenant pattern

Add `ctx["tenant"]` to every view via custom DI (see Custom integrations above), then use it in rate limiting and policies:

```python
@router.get("/items")
@rate_limit("1000/day", key=lambda req, ctx: f"tenant:{ctx['tenant_id']}")
def list_items(request, ctx):
    return Item.objects.filter(tenant=ctx["tenant"])
```

### Celery background task triggered by event

```python
from ninja_boost.events import event_bus

@event_bus.on("after_response")
def trigger_background_task(request, ctx, response, duration_ms, **kw):
    if request.path.startswith("/api/orders/") and request.method == "POST":
        if getattr(response, "status_code", 200) == 200:
            send_order_confirmation.delay(ctx.get("trace_id"))
```

---

## Testing

```python
# conftest.py
import pytest
from ninja_boost.conf import boost_settings
from ninja_boost.rate_limiting import _reset_backend

@pytest.fixture(autouse=True)
def reset_boost():
    boost_settings.reload()
    _reset_backend()
    yield
```

**Test rate limiting:**
```python
def test_rate_limit_enforced(client):
    with override_settings(NINJA_BOOST={"RATE_LIMIT": {"DEFAULT": "3/minute"}}):
        for _ in range(3):
            r = client.get("/api/items/", HTTP_AUTHORIZATION="Bearer demo")
            assert r.status_code == 200
        r = client.get("/api/items/", HTTP_AUTHORIZATION="Bearer demo")
        assert r.status_code == 429
```

**Test permissions:**
```python
def test_staff_only(client):
    r = client.get("/api/admin/", HTTP_AUTHORIZATION="Bearer demo")
    assert r.status_code == 403
```

**Test events:**
```python
def test_before_request_fires(client):
    seen = []
    @event_bus.on("before_request")
    def capture(request, ctx, **kw):
        seen.append(request.path)

    client.get("/api/items/", HTTP_AUTHORIZATION="Bearer demo")
    assert "/api/items/" in seen
    event_bus.off("before_request", capture)
```

**Test idempotency:**
```python
def test_idempotency_dedupes(client):
    key     = "test-uuid-key"
    headers = {"HTTP_AUTHORIZATION": "Bearer demo", "HTTP_X_IDEMPOTENCY_KEY": key}
    r1 = client.post("/api/payments/", data={"amount": 100}, **headers)
    r2 = client.post("/api/payments/", data={"amount": 100}, **headers)
    assert r1.json() == r2.json()
    assert r2["X-Idempotency-Replay"] == "true"
```

---

## Deployment

### Production settings

```python
NINJA_BOOST = {
    "AUTH": "ninja_boost.integrations.JWTAuth",
    "RESPONSE_WRAPPER": "ninja_boost.responses.wrap_response",
    "PAGINATION": "ninja_boost.pagination.auto_paginate",
    "DI": "ninja_boost.dependencies.inject_context",
    "RATE_LIMIT": {"BACKEND": "ninja_boost.rate_limiting.CacheBackend", "DEFAULT": "300/minute"},
    "METRICS": {"BACKEND": "ninja_boost.metrics.PrometheusBackend", "NAMESPACE": "myapi"},
    "DOCS": {"DISABLE_IN_PRODUCTION": True},
    "PLUGINS": ["myproject.plugins.SentryPlugin", "myproject.plugins.DatadogPlugin"],
}

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "ninja_boost.middleware.TracingMiddleware",
    "ninja_boost.lifecycle.LifecycleMiddleware",
    "ninja_boost.security_headers.SecurityHeadersMiddleware",
    ...
]
```

### Docker

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["gunicorn", "myproject.wsgi:application", "--workers", "4", "--bind", "0.0.0.0:8000"]
```

### ASGI (uvicorn)

```bash
uvicorn myproject.asgi:application --workers 4 --host 0.0.0.0 --port 8000 --loop uvloop
```

---

## Publishing to PyPI

### Prerequisites

```bash
pip install build twine
```

### Step 1 — Register on PyPI

1. Create account at [pypi.org](https://pypi.org)
2. Enable 2FA (required for all new packages)
3. Account Settings → API tokens → Add API token → set scope to project
4. Copy the `pypi-...` token

### Step 2 — Store credentials

**`~/.pypirc`:**
```ini
[pypi]
  username = __token__
  password = pypi-your-token-here
```

Or as environment variable:
```bash
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=pypi-your-token-here
```

### Step 3 — Clean build

```bash
rm -rf dist/ build/ src/*.egg-info
python -m build
ls dist/
# django_ninja_boost-0.3.0-py3-none-any.whl
# django-ninja-boost-0.3.0.tar.gz
```

### Step 4 — Test on TestPyPI first

```bash
twine upload --repository testpypi dist/*
pip install --index-url https://test.pypi.org/simple/ django-ninja-boost
python -c "import ninja_boost; print(ninja_boost.__version__)"
```

### Step 5 — Publish to PyPI

```bash
twine upload dist/*
```

Verify:
```bash
pip install django-ninja-boost
python -c "from ninja_boost import AutoAPI; print('OK')"
```

### Step 6 — Tag and automate

```bash
git tag v0.3.0 && git push origin v0.3.0
```

**GitHub Actions — Trusted Publishing (no secrets to rotate):**

```yaml
# .github/workflows/publish.yml
name: Publish to PyPI

on:
  push:
    tags: ["v*"]

jobs:
  publish:
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.12"}
      - run: pip install build && python -m build
      - uses: pypa/gh-action-pypi-publish@release/v1
```

Configure Trusted Publishing on PyPI dashboard → your project → Publishing → Add publisher → enter GitHub repo details. No `PYPI_TOKEN` secret needed.

---

## CLI reference

```bash
ninja-boost startproject myapi   # scaffold complete Django project
ninja-boost startapp orders      # scaffold new app in apps/orders/
ninja-boost config               # print starter NINJA_BOOST settings block
```

---

## Security considerations

1. **Replace `BearerTokenAuth`** in production — it accepts the literal string `"demo"`. Use `JWTAuth` or your own.
2. **Rate limit auth endpoints** — login and password-reset must have per-IP limits.
3. **Disable docs in production** — `NINJA_BOOST["DOCS"]["DISABLE_IN_PRODUCTION"] = True`.
4. **Use separate `JWT_SECRET_KEY`** — don't reuse Django's `SECRET_KEY` for JWTs.
5. **Store webhook secrets in env vars** — never hardcode. Rotate after any exposure.
6. **Switch to Redis rate limiting** in multi-process deployments — `InMemoryBackend` state is per-process.
7. **Enable `HSTS_PRELOAD`** only after ensuring your entire domain serves HTTPS — it's hard to undo.

---

## Performance notes

- **Offset pagination**: `COUNT(*) + LIMIT/OFFSET`. Fast for small offsets, degrades past ~100k rows. Use `@cursor_paginate` for deep pagination.
- **Rate limiting**: `InMemoryBackend` is O(n) in window size. For very high traffic, `CacheBackend` with Redis atomic increment is more efficient.
- **Event bus**: Handlers run synchronously in-band. Slow handlers delay responses. Offload long-running work to Celery.
- **Metrics labels**: Path normalization replaces `/items/42` with `/items/{id}` to prevent Prometheus cardinality explosion.
- **Structured logging**: `json.dumps` per record is fast for typical log volumes. At >100k req/s consider async logging or direct UDP to a collector.

---

## Troubleshooting & FAQ

**`ImproperlyConfigured: NINJA_BOOST is missing required keys`**
Provide all four core keys or remove the partial config to use defaults.

**Pagination applied to a single-object endpoint**
Add `paginate=False` to the decorator: `@router.post("/", paginate=False)`.

**`ctx` is missing or None**
Ensure you're using `AutoRouter` (from `ninja_boost`), not the plain `Router` from `ninja`.

**Rate limiting not shared across workers**
Switch from `InMemoryBackend` to `CacheBackend` (Redis).

**Health check returns 503**
One critical check is failing. Visit `/api/health/` for the full status with check details.

**JWT decodes but `ctx["user"]` is None**
Your `authenticate` method must return the decoded payload dict, not `True`.

---

## Comparison table

| Feature | Plain Django Ninja | ninja_boost |
|---------|:-------------------:|:-----------:|
| Response envelope | Manual | Auto |
| Offset pagination | Manual | Auto `?page=&size=` |
| Cursor pagination | Manual | `@cursor_paginate` |
| Trace ID | ❌ | UUID, `X-Trace-Id` |
| Auth wiring | Manual per router | Auto from settings |
| Rate limiting | External package | Built-in |
| Permissions | `if not user.is_staff` | `@require(IsStaff)` |
| Policy registry | ❌ | `BasePolicy` + registry |
| IoC / services | ❌ | `service_registry` |
| JSON logging | Manual | Auto-context formatter |
| Metrics | External package | Built-in adapters |
| Async views | Supported | Auto-detected, auto-wrapped |
| Health checks | ❌ | `/live` + `/ready` |
| Response caching | Manual | `@cache_response` |
| API versioning | Manual | `versioned_api` + decorators |
| Docs security | ❌ | `DocGuard` + IP allowlist |
| Idempotency | ❌ | `@idempotent` |
| Webhook verification | ❌ | Stripe/GitHub/Slack built-in |
| Security headers | ❌ | `SecurityHeadersMiddleware` |
| Audit logging | ❌ | `@audit_log` + DB backend |
| Plugin system | ❌ | `BoostPlugin` architecture |
| Event bus | ❌ | `@event_bus.on(...)` |
| CLI scaffolding | ❌ | `ninja-boost startproject` |
| Production JWT auth | Example code only | `JWTAuth` + `create_jwt_token` |

---

## Changelog

### 0.3.0 (2026-02-24)

- **New:** `webhook.py` — `@stripe_webhook`, `@github_webhook`, `@slack_webhook`, `@verify_webhook`
- **New:** `cursor_paginate` — O(1) keyset pagination decorator
- **New:** `JWTAuth` + `create_jwt_token` in `integrations.py` — production JWT authentication
- **Fix:** `idempotent` and `IdempotencyMiddleware` now exported from `__init__.py`
- **Bump:** version to `0.3.0` in `pyproject.toml` and `__init__.py`

### 0.2.0 (2026-02-24)

- New: `events.py`, `plugins.py`, `rate_limiting.py`, `permissions.py`, `policies.py`
- New: `services.py`, `logging_structured.py`, `metrics.py`, `async_support.py`
- New: `lifecycle.py`, `health.py`, `caching.py`, `versioning.py`, `docs.py`
- New: `idempotency.py`, `security_headers.py`, `audit.py`
- Updated: `api.py`, `router.py`, `dependencies.py`, `middleware.py`, `exceptions.py`, `apps.py`, `conf.py`

### 0.1.0

- `AutoAPI`, `AutoRouter`, `TracingMiddleware`, `inject_context`, `auto_paginate`
- `register_exception_handlers`, `BearerTokenAuth`, `ninja-boost` CLI

---

## Contributing

```bash
git clone https://github.com/bensylvenus/django-ninja-boost
cd django-ninja-boost
pip install -e ".[dev]"
pytest
```

Areas especially welcome: additional permission classes, CloudWatch/OpenTelemetry metrics backends, DRF migration guide, additional language documentation.

---

## License

MIT License — see [LICENSE](LICENSE).

---

*Built with ❤️ for the Django community. If ninja_boost saves you time, give it a ⭐ on GitHub.*
