# django-ninja-boost

**The production automation layer Django Ninja was always missing.**

Auto-wires everything a real API needs — auth, envelopes, pagination, DI, rate limiting, permissions, policies, services, events, async, structured logging, metrics, health checks, caching, versioning, and docs hardening — configure once, build forever.

[![PyPI version](https://img.shields.io/pypi/v/django-ninja-boost.svg)](https://pypi.org/project/django-ninja-boost/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Django 4.2+](https://img.shields.io/badge/django-4.2+-green.svg)](https://djangoproject.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://github.com/bensylvenus/django-ninja-boost/actions/workflows/test.yml/badge.svg)](https://github.com/bensylvenus/django-ninja-boost/actions)
[![Coverage](https://img.shields.io/badge/coverage-90%25+-brightgreen.svg)](https://github.com/bensylvenus/django-ninja-boost/actions)

---

## Table of Contents

- [What is this?](#what-is-this)
- [The problem it solves](#the-problem-it-solves)
- [Feature overview](#feature-overview)
- [Installation](#installation)
- [Quick Start (5 minutes)](#quick-start-5-minutes)
- [Adding to an existing project](#adding-to-an-existing-project)
- [Feature reference](#feature-reference)
  - [AutoAPI — response envelope + auth](#autoapi--response-envelope--auth)
  - [AutoRouter — DI + pagination + auth](#autorouter--di--pagination--auth)
  - [Context injection (ctx)](#context-injection-ctx)
  - [Auto-pagination](#auto-pagination)
  - [TracingMiddleware](#tracingmiddleware)
  - [Exception handlers](#exception-handlers)
  - [Event bus](#event-bus)
  - [Plugin system](#plugin-system)
  - [Rate limiting](#rate-limiting)
  - [Declarative permissions](#declarative-permissions)
  - [Policy registry](#policy-registry)
  - [Service registry (DI container)](#service-registry-di-container)
  - [Structured logging](#structured-logging)
  - [Metrics hooks](#metrics-hooks)
  - [Async support](#async-support)
  - [Lifecycle middleware](#lifecycle-middleware)
  - [Health checks](#health-checks)
  - [Response caching](#response-caching)
  - [API versioning](#api-versioning)
  - [Docs hardening](#docs-hardening)
- [Configuration reference](#configuration-reference)
- [Custom integrations](#custom-integrations)
- [Real-world patterns](#real-world-patterns)
- [Testing](#testing)
- [Deployment](#deployment)
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

It does **not** replace Django Ninja — it extends it. Every argument NinjaAPI and Router accept still works. You can migrate one router at a time. Un-migrated routes keep working.

```python
# Before: repeated ceremony on every router
from ninja import NinjaAPI, Router
from ninja.security import HttpBearer

class JWTAuth(HttpBearer):
    def authenticate(self, request, token): ...   # copied into every project

router = Router()

@router.get("/users", auth=JWTAuth())
def list_users(request):
    page  = int(request.GET.get("page", 1))       # manually paginated
    size  = int(request.GET.get("size", 20))       # every time
    start = (page - 1) * size
    total = User.objects.count()
    data  = list(User.objects.all()[start:start+size])
    return {"items": data, "total": total, "page": page, "size": size, "pages": ...}


# After: declare once, works everywhere
from ninja_boost import AutoAPI, AutoRouter

api    = AutoAPI()
router = AutoRouter(tags=["Users"])

@router.get("/users")
def list_users(request, ctx):                     # ctx injected: user, ip, trace_id
    return User.objects.all()                     # auto-paginated, auto-wrapped
```

---

## The problem it solves

Every real-world Django Ninja project re-implements the same cross-cutting concerns:

| Concern | Without ninja-boost | With ninja-boost |
|---------|--------------------|--------------------|
| Auth | Copy auth class to every project | Declare once in `settings.py` |
| Response shape | `{"ok": True, "data": result}` by hand | Automatic |
| Pagination | 6 lines per list endpoint | Auto-applied, opt-out per route |
| Request context | `request.auth`, `request.META["REMOTE_ADDR"]`, `request.trace_id` | `ctx["user"]`, `ctx["ip"]`, `ctx["trace_id"]` |
| Rate limiting | Third-party package, 20 lines per route | `@rate_limit("100/hour")` |
| Permissions | Inline `if not user.is_staff: raise` | `@require(IsStaff)` |
| Policies | Scattered per-view logic | `policy_registry.authorize(req, ctx, "order", "update", obj=o)` |
| Event hooks | Monkey-patching | `@event_bus.on("before_request")` |
| Structured logging | Custom formatter wired manually | One LOGGING entry |
| Metrics | SDK-specific setup per project | `@track("my_op")` or backend config |
| Health checks | DIY | `api.add_router("/health", health_router)` |
| Caching | Manual cache key management | `@cache_response(ttl=60)` |

---

## Feature overview

**v0.2.0 — 26 modules**

| # | Module | What it does |
|---|--------|-------------|
| 1 | `AutoAPI` | NinjaAPI subclass: default auth, response envelope, plugin startup |
| 2 | `AutoRouter` | Router subclass: auth, DI, pagination, global rate limit per-operation |
| 3 | `events` | Pub/sub event bus with sync + async dispatch, 9 built-in events |
| 4 | `plugins` | Plugin base class + registry, auto-wired to event bus |
| 5 | `rate_limiting` | `@rate_limit("N/period")`, in-memory + cache backends |
| 6 | `permissions` | `@require(IsStaff)`, composable with `&` `\|` `~` |
| 7 | `policies` | Resource policy registry, `@policy("order", "delete")` |
| 8 | `services` | Service DI container, singleton + scoped, `ctx["services"]` |
| 9 | `logging_structured` | JSON log formatter, request context auto-binding, access log |
| 10 | `metrics` | Prometheus / StatsD / logging backends, `@track`, active-request gauge |
| 11 | `async_support` | Async DI, async pagination, async rate limit, async permissions |
| 12 | `lifecycle` | `LifecycleMiddleware` — single point for all request/response hooks |
| 13 | `health` | `GET /health/live` + `/health/ready`, k8s-compatible, custom checks |
| 14 | `caching` | `@cache_response(ttl=60, key="user")`, `CacheManager` |
| 15 | `versioning` | `VersionedRouter`, `@deprecated`, `@require_version`, `versioned_api()` |
| 16 | `docs` | IP allowlist, staff-only docs, disable in production, security schemes |
| 17 | `dependencies` | `inject_context` — the `ctx` injection decorator |
| 18 | `pagination` | `auto_paginate` — transparent page/size pagination for lists + QuerySets |
| 19 | `middleware` | `TracingMiddleware` — UUID trace ID + X-Trace-Id header |
| 20 | `exceptions` | `register_exception_handlers` — standard error envelopes |
| 21 | `responses` | `wrap_response` — `{"ok": True, "data": ...}` |
| 22 | `conf` | `BoostSettings` — lazy settings proxy with defaults |
| 23 | `apps` | `NinjaBoostConfig` — auto-loads plugins, policies, services on startup |
| 24 | `integrations` | `BearerTokenAuth` — demo auth backend |
| 25 | `cli` | `ninja-boost startproject / startapp / config` |

---

## Installation

```bash
pip install django-ninja-boost
```

Optional backends:

```bash
pip install "django-ninja-boost[prometheus]"   # Prometheus metrics
pip install "django-ninja-boost[statsd]"       # StatsD metrics
pip install "django-ninja-boost[redis]"        # Redis rate limiting + caching
pip install "django-ninja-boost[all]"          # Everything
```

Add to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    ...
    "ninja_boost",
]
```

---

## Quick Start (5 minutes)

### Option A — Scaffold a new project

```bash
pip install django-ninja-boost
ninja-boost startproject myapi
cd myapi
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

This creates a complete, runnable project. Open `http://localhost:8000/api/docs` to see the interactive docs.

### Option B — Manual setup

**1. settings.py**

```python
INSTALLED_APPS = [
    ...
    "ninja_boost",
]

MIDDLEWARE = [
    ...
    "ninja_boost.middleware.TracingMiddleware",       # adds trace_id to every request
    "ninja_boost.lifecycle.LifecycleMiddleware",     # fires before/after events
]

NINJA_BOOST = {
    "AUTH":             "myproject.auth.JWTAuth",    # your auth class
    "RESPONSE_WRAPPER": "ninja_boost.responses.wrap_response",
    "PAGINATION":       "ninja_boost.pagination.auto_paginate",
    "DI":               "ninja_boost.dependencies.inject_context",
}
```

**2. urls.py**

```python
from django.urls import path
from ninja_boost import AutoAPI
from ninja_boost.exceptions import register_exception_handlers
from ninja_boost.health import health_router

api = AutoAPI(title="My API", version="1.0")
register_exception_handlers(api)
api.add_router("/health", health_router)

from apps.users.routers import router as users_router
api.add_router("/users", users_router)

urlpatterns = [
    path("api/", api.urls),
]
```

**3. apps/users/routers.py**

```python
from ninja_boost import AutoRouter
from .schemas import UserOut, UserCreate
from .services import UserService

router = AutoRouter(tags=["Users"])

@router.get("/", response=list[UserOut])
def list_users(request, ctx):
    return UserService.all()          # auto-paginated

@router.get("/{id}", response=UserOut)
def get_user(request, ctx, id: int):
    return UserService.get(id)

@router.post("/", response=UserOut, paginate=False)
def create_user(request, ctx, payload: UserCreate):
    return UserService.create(payload)
```

That's it. You now have auth, pagination, response envelopes, tracing, and structured logging — with zero per-route boilerplate.

---

## Adding to an existing project

ninja-boost is designed for incremental adoption. You can migrate one router at a time without touching any other code.

```python
# Before
from ninja import Router
router = Router()

@router.get("/items", auth=JWTAuth())
def list_items(request): ...


# After — only change the import and class name
from ninja_boost import AutoRouter
router = AutoRouter()

@router.get("/items")
def list_items(request, ctx):   # add ctx param; auth now auto-wired
    ...
```

**Checklist:**
1. Replace `from ninja import Router` → `from ninja_boost import AutoRouter`
2. Add `ctx` as the second parameter to view functions
3. Access `ctx["user"]` instead of `request.auth`
4. Access `ctx["ip"]` instead of `request.META["REMOTE_ADDR"]`
5. Remove manual pagination boilerplate — it's automatic
6. Remove `auth=JWTAuth()` from every decorator — it's now in `NINJA_BOOST["AUTH"]`

---

## Feature reference

### AutoAPI — response envelope + auth

AutoAPI is a drop-in subclass of `NinjaAPI`. Every argument NinjaAPI accepts works unchanged.

```python
from ninja_boost import AutoAPI

api = AutoAPI(
    title="Bookstore API",
    version="2.1",
    description="Built with django-ninja-boost",
    docs_url="/docs",           # all NinjaAPI kwargs still work
    openapi_url="/openapi.json",
)
```

**What it adds automatically:**

1. Default auth from `settings.NINJA_BOOST["AUTH"]` — no more `auth=JWTAuth()` on every route
2. Response envelope: `{"ok": True, "data": <payload>}` on every success
3. Plugin `on_startup()` hooks called when the API instance is created
4. Documentation hardening if `NINJA_BOOST["DOCS"]` is configured

**Response envelope:**

```json
// Success
{"ok": true, "data": {"id": 1, "name": "Django"}}

// Paginated list
{"ok": true, "data": {"items": [...], "page": 1, "size": 20, "total": 142, "pages": 8}}

// Error
{"ok": false, "error": "Not found", "code": 404}
```

Override `RESPONSE_WRAPPER` for a custom shape:

```python
# myproject/responses.py
def my_wrapper(data):
    return {"success": True, "result": data, "timestamp": time.time()}

# settings.py
NINJA_BOOST = {"RESPONSE_WRAPPER": "myproject.responses.my_wrapper", ...}
```

---

### AutoRouter — DI + pagination + auth

```python
from ninja_boost import AutoRouter

router = AutoRouter(tags=["Items"])
```

**Per-operation flags** (pass as keyword args to the decorator):

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `inject` | bool | `True` | Apply `ctx` injection |
| `paginate` | bool | `True` | Apply auto-pagination |
| `auth` | auth class or `None` | from settings | Override auth for this route |

```python
@router.get("/health", auth=None, inject=False, paginate=False)
def health(request):
    return {"status": "ok"}

@router.post("/", response=ItemOut, paginate=False)
def create_item(request, ctx, payload: ItemCreate):
    return ItemService.create(payload)   # single object — skip pagination
```

---

### Context injection (ctx)

Every AutoRouter view receives a `ctx` dict as its second argument:

```python
@router.get("/me")
def me(request, ctx):
    user     = ctx["user"]       # from request.auth
    ip       = ctx["ip"]         # client IP, honours X-Forwarded-For
    trace_id = ctx["trace_id"]   # UUID from TracingMiddleware
    services = ctx["services"]   # service registry (if services are registered)
    return user
```

Access `ctx["services"]` to reach the service DI container:

```python
@router.get("/dashboard")
def dashboard(request, ctx):
    users  = ctx["services"]["users"].recent()
    orders = ctx["services"]["orders"].count_today()
    return {"users": users, "orders": orders}
```

Opt out of injection on a specific route:

```python
@router.get("/webhook", inject=False, auth=None, paginate=False)
def webhook(request):
    # raw request access — no ctx injected
    return {"received": True}
```

---

### Auto-pagination

Any view returning a list or Django QuerySet is automatically paginated. No code changes needed.

```python
@router.get("/products", response=list[ProductOut])
def list_products(request, ctx):
    return Product.objects.filter(active=True)   # QuerySet — paginated automatically
```

**Query parameters:** `?page=2&size=50`

**Response shape:**
```json
{
    "ok": true,
    "data": {
        "items":  [...],
        "page":   2,
        "size":   50,
        "total":  1423,
        "pages":  29
    }
}
```

**Performance:** Uses `.count()` + `LIMIT/OFFSET` — two SQL queries, never loads the full table.

**Opt out per route:**

```python
@router.post("/", response=ProductOut, paginate=False)
def create_product(request, ctx, payload: ProductCreate):
    return ProductService.create(payload)
```

**Custom pagination** — replace the paginator entirely:

```python
# myproject/pagination.py
def cursor_paginate(func):
    @wraps(func)
    def wrapper(request, *args, **kwargs):
        result = func(request, *args, **kwargs)
        cursor = request.GET.get("cursor")
        ...
    return wrapper

# settings.py
NINJA_BOOST = {"PAGINATION": "myproject.pagination.cursor_paginate", ...}
```

---

### TracingMiddleware

Adds a UUID trace ID to every request. Zero configuration.

```python
# settings.py
MIDDLEWARE = [
    ...
    "ninja_boost.middleware.TracingMiddleware",
]
```

- `request.trace_id` — available in every view
- `ctx["trace_id"]` — available when using AutoRouter
- `X-Trace-Id` response header — for APM tools and client-side correlation
- All log records during the request include the trace ID automatically (with `StructuredLoggingMiddleware`)

---

### Exception handlers

```python
from ninja_boost import AutoAPI
from ninja_boost.exceptions import register_exception_handlers

api = AutoAPI()
register_exception_handlers(api)
```

Error responses always follow the `{"ok": false, "error": "...", "code": N}` shape. Exception handlers emit `on_error` events for plugin/Sentry hooks automatically.

Raise errors in views using Django Ninja's `HttpError`:

```python
from ninja.errors import HttpError

@router.get("/{id}", response=UserOut)
def get_user(request, ctx, id: int):
    user = User.objects.filter(id=id).first()
    if not user:
        raise HttpError(404, "User not found")
    return user
```

---

### Event bus

The event bus is the backbone of ninja-boost's extensibility. Every lifecycle event fires through it. Subscribe from anywhere in your project code without modifying framework internals.

```python
from ninja_boost.events import event_bus

# Register a handler
@event_bus.on("before_request")
def log_incoming(request, ctx, **kw):
    print(f"[{ctx['trace_id']}] {request.method} {request.path}")

@event_bus.on("after_response")
def record_timing(request, ctx, response, duration_ms, **kw):
    print(f"→ {response.status_code}  {duration_ms:.1f}ms")

@event_bus.on("on_error")
def alert_on_error(request, ctx, exc, **kw):
    Sentry.capture_exception(exc)
```

**Built-in events:**

| Event constant | Emitted when |
|----------------|-------------|
| `BEFORE_REQUEST` | Before a view is called |
| `AFTER_RESPONSE` | After the response is built |
| `ON_ERROR` | On an unhandled exception |
| `ON_AUTH_FAILURE` | Auth returns None |
| `ON_RATE_LIMIT_EXCEEDED` | Rate limit breached |
| `ON_PERMISSION_DENIED` | Permission check fails |
| `ON_POLICY_DENIED` | Policy evaluation returns False |
| `ON_SERVICE_REGISTERED` | Service added to registry |
| `ON_PLUGIN_LOADED` | Plugin registered |

**Async handlers:**

```python
@event_bus.on("before_request")
async def async_handler(request, ctx, **kw):
    await some_async_operation()

# Fire with all async handlers running concurrently:
await event_bus.emit_async("before_request", request=request, ctx=ctx)
```

**Wildcard handler** (receives every event):

```python
@event_bus.on_any
def debug_all(event, **kw):
    print(f"Event: {event}")
```

**Always use `**kw`** in handlers — events may gain new fields in future versions without breaking your code.

---

### Plugin system

Plugins are classes that hook into the request lifecycle without forking the framework.

```python
from ninja_boost.plugins import BoostPlugin, plugin_registry

class AuditPlugin(BoostPlugin):
    name    = "audit"
    version = "1.0"

    def on_startup(self, api):
        print(f"Audit plugin attached to {api.title}")

    def on_request(self, request, ctx, **kw):
        AuditLog.objects.create(
            user_id = ctx["user"].get("id") if ctx["user"] else None,
            path    = request.path,
            ip      = ctx["ip"],
            method  = request.method,
        )

    def on_error(self, request, exc, ctx, **kw):
        sentry_sdk.capture_exception(exc)

    def on_response(self, request, response, ctx, duration_ms, **kw):
        if duration_ms > 1000:
            logger.warning("Slow response: %s %.0fms", request.path, duration_ms)

plugin_registry.register(AuditPlugin())
```

**Auto-load from settings:**

```python
NINJA_BOOST = {
    ...
    "PLUGINS": [
        "myproject.plugins.AuditPlugin",
        "myproject.plugins.SentryPlugin",
    ],
}
```

**Available plugin hooks:**

| Hook | Called when |
|------|-------------|
| `on_startup(api)` | `AutoAPI.__init__()` |
| `on_request(request, ctx)` | Before every view |
| `on_response(request, response, ctx, duration_ms)` | After every response |
| `on_error(request, exc, ctx)` | On unhandled exception |
| `on_auth_failure(request)` | Auth returns None |
| `on_rate_limit_exceeded(request, key, rate)` | Rate limit breached |
| `on_permission_denied(request, ctx, permission)` | Permission check fails |

Plugin exceptions are caught and logged — they can never crash the request cycle.

---

### Rate limiting

```python
from ninja_boost.rate_limiting import rate_limit

@router.get("/search")
@rate_limit("30/minute")                          # key = client IP (default)
def search(request, ctx, q: str): ...

@router.post("/login")
@rate_limit("5/minute", key="ip")                 # explicit IP key
def login(request, ctx, payload: LoginPayload): ...

@router.post("/send-email")
@rate_limit("10/hour", key="user")                # per authenticated user
def send_email(request, ctx, payload): ...

@router.get("/export")
@rate_limit("3/day", key=lambda req, ctx: f"org:{ctx['user'].get('org_id')}")
def export(request, ctx): ...                     # custom key function
```

**Rate strings:** `"N/second"`, `"N/minute"`, `"N/hour"`, `"N/day"`

**Key types:**

| Key | Identifies by |
|-----|--------------|
| `"ip"` (default) | Client IP address |
| `"user"` | Authenticated user ID (falls back to IP for anonymous) |
| callable | `fn(request, ctx) -> str` — any custom string |

**Backends:**

```python
# settings.py
NINJA_BOOST = {
    ...
    "RATE_LIMIT": {
        "DEFAULT": "200/minute",                            # global default (optional)
        "BACKEND": "ninja_boost.rate_limiting.InMemoryBackend",   # default
        # "BACKEND": "ninja_boost.rate_limiting.CacheBackend",    # Redis/Memcached
    },
}
```

`InMemoryBackend` uses a thread-safe sliding window counter — zero dependencies. Suitable for single-process deployments.

`CacheBackend` works across processes/servers using Django's cache framework. For Redis:

```bash
pip install "django-ninja-boost[redis]"
```

```python
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://localhost:6379/1",
    }
}
NINJA_BOOST = {
    "RATE_LIMIT": {"BACKEND": "ninja_boost.rate_limiting.CacheBackend"},
}
```

Clients exceeding the limit receive `HTTP 429` with a standard `{"ok": false, "error": "..."}` body.

---

### Declarative permissions

```python
from ninja_boost.permissions import require, IsAuthenticated, IsStaff, HasPermission, IsOwner

# Simple
@router.get("/admin/report")
@require(IsStaff)
def admin_report(request, ctx): ...

# Composition with & | ~
@router.get("/internal")
@require(IsAuthenticated & (IsStaff | HasPermission("myapp.view_internal")))
def internal_view(request, ctx): ...

# Object-level: caller must own the resource
@router.delete("/orders/{id}")
@require(IsOwner(lambda req, ctx, id, **kw: Order.objects.get(id=id).user_id))
def delete_order(request, ctx, id: int): ...

# Public endpoint (explicit)
@router.get("/public", auth=None)
@require(AllowAny)
def public(request, ctx): ...
```

**Built-in permission objects:**

| Permission | Allows |
|-----------|--------|
| `IsAuthenticated` | Any authenticated user |
| `IsStaff` | Staff users only (`is_staff=True`) |
| `IsSuperuser` | Superusers only (`is_superuser=True`) |
| `AllowAny` | Everyone (explicit public access) |
| `DenyAll` | Nobody (maintenance mode) |
| `HasPermission("codename")` | Users with the Django model permission |
| `IsOwner(fn)` | The user returned by `fn(request, ctx, **kwargs)` |

**Custom permission class:**

```python
from ninja_boost.permissions import BasePermission

class IsSubscribed(BasePermission):
    def has_permission(self, request, ctx) -> bool:
        user = ctx["user"]
        return isinstance(user, dict) and user.get("plan") != "free"

@router.get("/premium")
@require(IsAuthenticated & IsSubscribed())
def premium_content(request, ctx): ...
```

**Async permissions:**

```python
from ninja_boost.permissions import require_async

@router.get("/items")
@require_async(IsAuthenticated)
async def list_items_async(request, ctx): ...
```

---

### Policy registry

Policies encode all access rules for a resource in one class — analogous to Pundit (Ruby) or Laravel Policies.

```python
from ninja_boost.policies import BasePolicy, policy_registry

class OrderPolicy(BasePolicy):
    resource_name = "order"

    def before(self, request, ctx, action, obj=None):
        # Superusers bypass all checks
        if ctx["user"] and ctx["user"].get("is_superuser"):
            return True
        return None

    def view(self, request, ctx, obj=None) -> bool:
        return ctx["user"] is not None

    def create(self, request, ctx, obj=None) -> bool:
        return ctx["user"] is not None

    def update(self, request, ctx, obj=None) -> bool:
        return obj is not None and str(obj.user_id) == str(ctx["user"]["id"])

    def delete(self, request, ctx, obj=None) -> bool:
        return ctx["user"].get("is_staff", False)

policy_registry.register(OrderPolicy())
```

**Using policies in views:**

```python
# Imperative check (raises HttpError(403) on failure)
@router.put("/orders/{id}", response=OrderOut)
def update_order(request, ctx, id: int, payload: OrderUpdate):
    order = get_object_or_404(Order, id=id)
    policy_registry.authorize(request, ctx, "order", "update", obj=order)
    return OrderService.update(order, payload)

# Non-raising check
can_delete = policy_registry.can(request, ctx, "order", "delete", obj=order)

# Decorator style
from ninja_boost.policies import policy

@router.delete("/orders/{id}")
@policy("order", "delete", get_obj=lambda id, **kw: Order.objects.get(id=id))
def delete_order(request, ctx, id: int): ...
```

**Auto-load from settings:**

```python
NINJA_BOOST = {
    "POLICIES": [
        "apps.orders.policies.OrderPolicy",
        "apps.products.policies.ProductPolicy",
    ],
}
```

---

### Service registry (DI container)

Register services centrally; inject them into views via `ctx["services"]` or the `@inject_service` decorator.

```python
from ninja_boost.services import BoostService, service_registry

class UserService(BoostService):
    name = "users"

    def list_users(self):
        return User.objects.filter(is_active=True)

    def get_user(self, user_id: int):
        return get_object_or_404(User, id=user_id)

service_registry.register(UserService())
```

**In views:**

```python
@router.get("/users")
def list_users(request, ctx):
    svc = ctx["services"]["users"]
    return svc.list_users()
```

**With the `@inject_service` decorator:**

```python
from ninja_boost.services import inject_service

@router.get("/dashboard")
@inject_service("users", "orders")
def dashboard(request, ctx):
    users  = ctx["svc_users"].list_users()
    orders = ctx["svc_orders"].recent()
    return {"users": users, "orders": orders}
```

**Scoped services** (new instance per request):

```python
class RequestScopedService(BoostService):
    name   = "request_cache"
    scoped = True                         # ← fresh instance per request

    def __init__(self):
        self._data = {}

    def on_request(self, request, ctx):   # called at the start of each request
        self._data["user_id"] = ctx["user"]["id"] if ctx["user"] else None
```

**Auto-load from settings:**

```python
NINJA_BOOST = {
    "SERVICES": [
        "apps.users.services.UserService",
        "apps.orders.services.OrderService",
    ],
}
```

---

### Structured logging

Drop-in JSON logging with automatic request context enrichment.

```python
# settings.py
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json":    {"()": "ninja_boost.logging_structured.StructuredJsonFormatter"},
        "verbose": {"()": "ninja_boost.logging_structured.StructuredVerboseFormatter"},  # dev
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "json"},
    },
    "root":    {"handlers": ["console"], "level": "INFO"},
    "loggers": {"ninja_boost": {"level": "DEBUG"}},
}

MIDDLEWARE = [
    ...
    "ninja_boost.middleware.TracingMiddleware",
    "ninja_boost.logging_structured.StructuredLoggingMiddleware",
]
```

**Every log record automatically includes:**

```json
{
  "timestamp": "2026-02-24T14:30:00.123Z",
  "level":     "INFO",
  "logger":    "apps.orders",
  "message":   "Order created",
  "trace_id":  "a3f8c12d44e1...",
  "method":    "POST",
  "path":      "/api/orders",
  "user_id":   42,
  "ip":        "203.0.113.1"
}
```

**Access log (automatic, one line per request):**

```json
{
  "timestamp":   "2026-02-24T14:30:00.456Z",
  "level":       "INFO",
  "logger":      "ninja_boost.access",
  "message":     "POST /api/orders → 201 (12.4ms)",
  "http_status": 201,
  "duration_ms": 12.4,
  "trace_id":    "a3f8c12d..."
}
```

Works correctly in async views — uses `contextvars` internally, not threadlocals.

---

### Metrics hooks

Pluggable metrics with zero-dep logging backend included.

```python
# settings.py — Prometheus
NINJA_BOOST = {
    "METRICS": {
        "BACKEND":   "ninja_boost.metrics.PrometheusBackend",
        "NAMESPACE": "myapi",
    }
}
```

```bash
pip install "django-ninja-boost[prometheus]"
```

**Metrics emitted automatically:**

| Metric | Type | Labels |
|--------|------|--------|
| `{ns}_request_total` | counter | method, path, status |
| `{ns}_request_duration_ms` | histogram | method, path |
| `{ns}_request_errors_total` | counter | method, path, status |
| `{ns}_active_requests` | gauge | — |
| `{ns}_unhandled_errors_total` | counter | error_type |

**Manual metrics in views:**

```python
from ninja_boost.metrics import metrics

@router.post("/checkout")
def checkout(request, ctx, payload: CartPayload):
    result = OrderService.checkout(payload)
    metrics.increment("orders_created", labels={"tier": ctx["user"]["tier"]})
    with metrics.timer("checkout_duration_ms"):
        ...
    return result
```

**Per-function tracking:**

```python
from ninja_boost.metrics import track

@router.get("/products")
@track("list_products")                   # records call count + duration
def list_products(request, ctx): ...
```

**StatsD backend:**

```python
NINJA_BOOST = {
    "METRICS": {
        "BACKEND":   "ninja_boost.metrics.StatsDBackend",
        "HOST":      "localhost",
        "PORT":      8125,
        "NAMESPACE": "myapi",
    }
}
```

**Logging backend (zero deps, dev/CI):**

```python
NINJA_BOOST = {
    "METRICS": {"BACKEND": "ninja_boost.metrics.LoggingBackend"}
}
```

---

### Async support

Write `async def` views without any decorator changes. ninja-boost detects async views automatically.

```python
@router.get("/items")
async def list_items(request, ctx):
    items = await Item.objects.filter(active=True).acount()  # Django 4.1+ async ORM
    return await Item.objects.filter(active=True)            # auto-paginated

@router.get("/{id}")
async def get_item(request, ctx, id: int):
    item = await Item.objects.aget(id=id)
    return item
```

**What changes automatically with `async def`:**

- `inject_context` → `async_inject_context`
- `auto_paginate` → `async_paginate` (uses Django's `acount()` + async iteration)
- Rate limit backend called in thread executor (avoids blocking event loop)
- Context var propagation is safe in async contexts

**ASGI server setup:**

```bash
pip install uvicorn
uvicorn myproject.asgi:application --host 0.0.0.0 --port 8000 --workers 4
```

```python
# asgi.py
import os
from django.core.asgi import get_asgi_application
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")
application = get_asgi_application()
```

**Async tracing middleware** (for pure ASGI stacks):

```python
MIDDLEWARE = [
    "ninja_boost.async_support.AsyncTracingMiddleware",  # use instead of TracingMiddleware
    "ninja_boost.lifecycle.LifecycleMiddleware",
]
```

---

### Lifecycle middleware

`LifecycleMiddleware` is a single middleware that coordinates all cross-cutting concerns at the request/response boundary. Install it and everything else wires up automatically.

```python
MIDDLEWARE = [
    ...
    "ninja_boost.middleware.TracingMiddleware",       # sets trace_id (required first)
    "ninja_boost.lifecycle.LifecycleMiddleware",     # ← coordinates everything else
]
```

**What it does per request:**

1. Binds trace_id, method, path, user_id into the log context var
2. Increments the `active_requests` gauge
3. Emits `before_request` event (fires all registered handlers and plugins)
4. Calls the view
5. Records response time
6. Decrements `active_requests`, emits `request_total` counter
7. Emits `after_response` event
8. Attaches `X-RateLimit-Limit` and `X-RateLimit-Remaining` headers
9. Writes the structured access log line
10. Clears the log context var

Supports both sync (WSGI) and async (ASGI) stacks.

---

### Health checks

Production-ready health endpoints compatible with Kubernetes, Docker, AWS ALB, GCP Cloud Run, and any uptime monitor.

```python
from ninja_boost.health import health_router
api.add_router("/health", health_router, auth=None)
```

**Endpoints:**

- `GET /health/live` — liveness probe (always 200 if process is running)
- `GET /health/ready` — readiness probe (runs all checks, 200 or 503)
- `GET /health/` — alias for liveness

**Default checks (run on `/health/ready`):**

| Check | Critical | What it tests |
|-------|----------|---------------|
| `database` | Yes | `SELECT 1` via Django ORM |
| `cache` | No | Write + read from default cache |
| `migrations` | No | No unapplied migrations |

**Custom checks:**

```python
from ninja_boost.health import register_check

@register_check("redis")
def check_redis():
    from django.core.cache import cache
    cache.set("health:ping", 1, timeout=5)
    assert cache.get("health:ping") == 1

@register_check("celery", critical=False)        # degraded, not down
def check_celery():
    from myapp.celery import app
    result = app.control.ping(timeout=1.0)
    assert result, "No Celery workers responding"

@register_check("external_api", critical=False)
def check_payment_gateway():
    import requests
    r = requests.get("https://status.stripe.com/api/v2/status.json", timeout=3)
    assert r.status_code == 200
```

**Kubernetes probe config:**

```yaml
livenessProbe:
  httpGet:
    path: /api/health/live
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 30

readinessProbe:
  httpGet:
    path: /api/health/ready
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10
  failureThreshold: 3
```

---

### Response caching

Cache GET responses to avoid redundant database queries.

```python
from ninja_boost.caching import cache_response

@router.get("/products")
@cache_response(ttl=300)                          # cache 5 minutes, key = URL + query
def list_products(request, ctx): ...

@router.get("/categories")
@cache_response(ttl=3600, key="path")             # cache 1 hour per path (ignores query)
def list_categories(request, ctx): ...

@router.get("/me/wishlist")
@cache_response(ttl=120, key="user")              # per authenticated user
def my_wishlist(request, ctx): ...

@router.get("/leaderboard")
@cache_response(
    ttl=30,
    key=lambda req, ctx: f"leaderboard:{ctx['user'].get('tenant_id')}",
)
def leaderboard(request, ctx): ...               # custom key function
```

**Configuration:**

```python
NINJA_BOOST = {
    "CACHE": {
        "BACKEND": "default",     # Django cache alias
        "PREFIX":  "boost:",
        "ENABLED": True,
    }
}
```

**Invalidation:**

```python
from ninja_boost.caching import cache_manager

cache_manager.invalidate("path", "/api/products")
cache_manager.invalidate_prefix("leaderboard:")
cache_manager.clear_all()
```

---

### API versioning

**Strategy A — URL prefix (recommended):**

```python
from ninja_boost.versioning import versioned_api

apis = versioned_api(["v1", "v2"], title="Bookstore API")
apis["v1"].add_router("/books", books_v1_router)
apis["v2"].add_router("/books", books_v2_router)

urlpatterns = [
    path(f"api/{ver}/", api.urls)
    for ver, api in apis.items()
]
```

**Strategy B — Header-based (`X-API-Version`):**

```python
from ninja_boost.versioning import require_version

@router.get("/users")
@require_version("2.0", header="X-API-Version")
def list_users_v2(request, ctx): ...
```

**Strategy C — `VersionedRouter`:**

```python
from ninja_boost.versioning import VersionedRouter

users = VersionedRouter(tags=["Users"])

@users.v1.get("/")
def list_users_v1(request, ctx): ...

@users.v2.get("/")
def list_users_v2(request, ctx): ...

api_v1.add_router("/users", users.v1)
api_v2.add_router("/users", users.v2)
```

**Deprecation headers:**

```python
from ninja_boost.versioning import deprecated

@router.get("/v1/old-endpoint")
@deprecated(sunset="2026-12-31", replacement="/api/v2/users")
def old_endpoint(request, ctx): ...
```

Responses include standard RFC 8594 headers:
```
Deprecation: true
Sunset: 2026-12-31
Link: </api/v2/users>; rel="successor-version"
```

---

### Docs hardening

Control who can access `/api/docs` and `/api/redoc`.

```python
NINJA_BOOST = {
    "DOCS": {
        "ENABLED":               True,           # False → 404 for docs URLs
        "REQUIRE_STAFF":         False,          # True → only staff users
        "REQUIRE_AUTH":          False,          # True → any authenticated user
        "ALLOWED_IPS":           [],             # ["10.0.0.0/8", "127.0.0.1"]
        "DISABLE_IN_PRODUCTION": False,          # True → disabled when DEBUG=False
    }
}
```

Or programmatic control:

```python
from ninja_boost.docs import harden_docs, DocGuard

harden_docs(api, guard=DocGuard(
    require_staff=True,
    allowed_ips=["10.0.0.0/8"],
    disable_in_production=True,
))
```

**Add Bearer auth to the OpenAPI schema:**

```python
from ninja_boost.docs import add_security_scheme

add_security_scheme(api, name="BearerAuth", scheme_type="http",
                    scheme="bearer", bearer_format="JWT")
```

---

## Configuration reference

Complete `NINJA_BOOST` settings dict with all options:

```python
NINJA_BOOST = {
    # ── Core ───────────────────────────────────────────────────────────────
    # Auth class (dotted path). Any HttpBearer/APIKeyHeader subclass.
    "AUTH":             "ninja_boost.integrations.BearerTokenAuth",

    # Response wrapper function (data: Any) -> dict
    "RESPONSE_WRAPPER": "ninja_boost.responses.wrap_response",

    # Pagination decorator for list/QuerySet return values
    "PAGINATION":       "ninja_boost.pagination.auto_paginate",

    # Context injection decorator (adds ctx to every view)
    "DI":               "ninja_boost.dependencies.inject_context",

    # ── Rate limiting ──────────────────────────────────────────────────────
    "RATE_LIMIT": {
        "DEFAULT":  None,     # "200/minute" — applied globally (per-route @rate_limit wins)
        "BACKEND":  "ninja_boost.rate_limiting.InMemoryBackend",
        # "BACKEND": "ninja_boost.rate_limiting.CacheBackend",
    },

    # ── Metrics ────────────────────────────────────────────────────────────
    "METRICS": {
        "BACKEND":   None,    # "ninja_boost.metrics.PrometheusBackend"
        "NAMESPACE": "ninja_boost",
    },

    # ── Response caching ───────────────────────────────────────────────────
    "CACHE": {
        "BACKEND": "default",   # Django cache alias
        "PREFIX":  "boost:",
        "ENABLED": True,
    },

    # ── Documentation hardening ────────────────────────────────────────────
    "DOCS": {
        "ENABLED":               True,
        "REQUIRE_STAFF":         False,
        "REQUIRE_AUTH":          False,
        "ALLOWED_IPS":           [],
        "DISABLE_IN_PRODUCTION": False,
        "TITLE":                 None,    # Override OpenAPI title
        "DESCRIPTION":           None,
        "VERSION":               None,
        "SERVERS":               [],      # [{"url": "https://api.example.com"}]
    },

    # ── Auto-loaded on startup ─────────────────────────────────────────────
    "PLUGINS": [
        # "myproject.plugins.AuditPlugin",
    ],

    "POLICIES": [
        # "apps.orders.policies.OrderPolicy",
    ],

    "SERVICES": [
        # "apps.users.services.UserService",
    ],
}
```

---

## Custom integrations

### Custom auth (JWT)

```python
# myproject/auth.py
import jwt
from ninja.security import HttpBearer
from django.conf import settings

class JWTAuth(HttpBearer):
    def authenticate(self, request, token: str):
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.DecodeError:
            return None

# settings.py
NINJA_BOOST = {
    "AUTH": "myproject.auth.JWTAuth",
    ...
}
```

### Django session auth

```python
# myproject/auth.py
from ninja.security import django_auth

# Use Django's built-in session authentication:
NINJA_BOOST = {
    "AUTH": "ninja.security.django_auth",   # built-in to Django Ninja
    ...
}
```

### API key auth

```python
# myproject/auth.py
from ninja.security import APIKeyHeader

class ApiKeyAuth(APIKeyHeader):
    param_name = "X-API-Key"

    def authenticate(self, request, key: str):
        try:
            return ApiKey.objects.select_related("user").get(key=key, active=True)
        except ApiKey.DoesNotExist:
            return None
```

### Custom response envelope

```python
# myproject/responses.py
import time

def branded_response(data):
    return {
        "success": True,
        "result":  data,
        "ts":      time.time(),
        "api":     "MyAPI/2.0",
    }
```

### Custom DI context

```python
# myproject/dependencies.py
from functools import wraps

def rich_context(func):
    @wraps(func)
    def wrapper(request, *args, **kwargs):
        ctx = {
            "user":       getattr(request, "auth", None),
            "ip":         request.META.get("REMOTE_ADDR"),
            "trace_id":   getattr(request, "trace_id", None),
            "tenant_id":  request.META.get("HTTP_X_TENANT_ID"),
            "locale":     request.META.get("HTTP_ACCEPT_LANGUAGE", "en"),
        }
        return func(request, ctx, *args, **kwargs)
    return wrapper

# settings.py
NINJA_BOOST = {"DI": "myproject.dependencies.rich_context", ...}
```

---

## Real-world patterns

### Sentry integration plugin

```python
import sentry_sdk
from ninja_boost.plugins import BoostPlugin, plugin_registry

class SentryPlugin(BoostPlugin):
    name = "sentry"

    def on_error(self, request, exc, ctx, **kw):
        with sentry_sdk.push_scope() as scope:
            scope.set_user(ctx.get("user"))
            scope.set_tag("trace_id", ctx.get("trace_id"))
            scope.set_tag("path", request.path)
            sentry_sdk.capture_exception(exc)

plugin_registry.register(SentryPlugin())
```

### Multi-tenant APIs

```python
class TenantRateLimit(BoostPlugin):
    name = "tenant_rate_limit"

    def on_request(self, request, ctx, **kw):
        tenant_id = request.META.get("HTTP_X_TENANT_ID")
        if not tenant_id:
            return
        plan = TenantPlan.get(tenant_id)
        rate = {"free": "60/hour", "pro": "6000/hour", "enterprise": "60000/hour"}[plan]
        from ninja_boost.rate_limiting import rate_limit, _get_backend, _parse_rate
        limit, window = _parse_rate(rate)
        backend = _get_backend()
        allowed, _, _ = backend.is_allowed(f"tenant:{tenant_id}", limit, window)
        if not allowed:
            from ninja.errors import HttpError
            raise HttpError(429, "Tenant rate limit exceeded")
```

### Background task integration (Celery)

```python
from ninja_boost.events import event_bus

@event_bus.on("after_response")
def maybe_enqueue_task(request, ctx, response, duration_ms, **kw):
    # Fire analytics task after every API call (non-blocking)
    if response.status_code == 201 and "/orders" in request.path:
        from apps.analytics.tasks import track_order_created
        track_order_created.delay(
            user_id=ctx["user"]["id"],
            trace_id=ctx["trace_id"],
        )
```

### Role-based access control

```python
from ninja_boost.permissions import BasePermission

class HasRole(BasePermission):
    def __init__(self, *roles: str):
        self._roles = set(roles)

    def has_permission(self, request, ctx) -> bool:
        user = ctx.get("user")
        if not user:
            return False
        user_roles = set(user.get("roles", []) if isinstance(user, dict)
                         else getattr(user, "roles", []))
        return bool(self._roles & user_roles)

CanEditContent = IsAuthenticated & HasRole("editor", "admin")
CanPublish     = IsAuthenticated & HasRole("publisher", "admin")

@router.put("/{id}/publish")
@require(CanPublish)
def publish_article(request, ctx, id: int): ...
```

### File uploads

```python
from ninja import File
from ninja.files import UploadedFile
from ninja_boost import AutoRouter

router = AutoRouter(tags=["Files"])

@router.post("/upload", paginate=False)
def upload_file(request, ctx, file: UploadedFile = File(...)):
    # Standard Django Ninja file upload — works unchanged with AutoRouter
    saved_path = FileService.save(file, owner=ctx["user"]["id"])
    return {"path": saved_path, "size": file.size}
```

---

## Testing

```bash
pip install "django-ninja-boost[dev]"
pytest
```

**Test configuration (conftest.py):**

```python
import django
from django.conf import settings

def pytest_configure():
    settings.configure(
        INSTALLED_APPS=["django.contrib.contenttypes", "django.contrib.auth", "ninja_boost"],
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
        NINJA_BOOST={
            "AUTH":             "ninja_boost.integrations.BearerTokenAuth",
            "RESPONSE_WRAPPER": "ninja_boost.responses.wrap_response",
            "PAGINATION":       "ninja_boost.pagination.auto_paginate",
            "DI":               "ninja_boost.dependencies.inject_context",
            "RATE_LIMIT":       {"ENABLED": False},   # ← disable in tests
            "METRICS":          {"BACKEND": "ninja_boost.metrics.LoggingBackend"},
        },
    )
    django.setup()
```

**Test patterns:**

```python
from ninja.testing import TestClient
from ninja_boost import AutoAPI, AutoRouter
from ninja_boost.exceptions import register_exception_handlers

def test_list_items():
    api    = AutoAPI()
    router = AutoRouter()
    register_exception_handlers(api)

    @router.get("/items")
    def list_items(request, ctx):
        return [{"id": 1, "name": "Widget"}]

    api.add_router("/items", router)
    client = TestClient(api)

    resp = client.get("/items", headers={"Authorization": "Bearer demo"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["items"][0]["id"] == 1

def test_rate_limit():
    from ninja_boost.rate_limiting import _reset_backend
    _reset_backend()                               # fresh backend per test

    @router.get("/limited")
    @rate_limit("2/minute")
    def limited(request, ctx): return {"ok": True}

    for i in range(2):
        resp = client.get("/limited", headers={"Authorization": "Bearer demo"})
        assert resp.status_code == 200

    resp = client.get("/limited", headers={"Authorization": "Bearer demo"})
    assert resp.status_code == 429

def test_permission_denied():
    @router.get("/admin")
    @require(IsStaff)
    def admin_view(request, ctx): return {"data": "secret"}

    resp = client.get("/admin", headers={"Authorization": "Bearer demo"})
    assert resp.status_code == 403
    assert resp.json()["ok"] is False
```

---

## Deployment

### Production settings

```python
# myproject/settings/production.py
from .base import *

DEBUG = False

NINJA_BOOST = {
    "AUTH":             "myproject.auth.JWTAuth",
    "RESPONSE_WRAPPER": "ninja_boost.responses.wrap_response",
    "PAGINATION":       "ninja_boost.pagination.auto_paginate",
    "DI":               "ninja_boost.dependencies.inject_context",

    "RATE_LIMIT": {
        "DEFAULT": "200/minute",
        "BACKEND": "ninja_boost.rate_limiting.CacheBackend",    # Redis in production
    },

    "METRICS": {
        "BACKEND":   "ninja_boost.metrics.PrometheusBackend",
        "NAMESPACE": "myapi",
    },

    "DOCS": {
        "REQUIRE_STAFF":         True,          # staff only in production
        "DISABLE_IN_PRODUCTION": False,         # change to True for fully private APIs
    },

    "PLUGINS": [
        "myproject.plugins.SentryPlugin",
        "myproject.plugins.AuditPlugin",
    ],
}

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "ninja_boost.middleware.TracingMiddleware",
    "ninja_boost.lifecycle.LifecycleMiddleware",
]
```

### Docker

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN python manage.py collectstatic --noinput

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/api/health/live || exit 1

CMD ["gunicorn", "myproject.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "4", \
     "--timeout", "30", \
     "--access-logfile", "-"]
```

### ASGI with uvicorn

```bash
pip install uvicorn[standard]
uvicorn myproject.asgi:application --host 0.0.0.0 --port 8000 --workers 4 --proxy-headers
```

### Environment variables

```python
import os

NINJA_BOOST = {
    "AUTH": os.environ.get("API_AUTH_CLASS", "myproject.auth.JWTAuth"),
    "RATE_LIMIT": {
        "DEFAULT": os.environ.get("API_RATE_LIMIT", "200/minute"),
        "BACKEND": (
            "ninja_boost.rate_limiting.CacheBackend"
            if os.environ.get("REDIS_URL")
            else "ninja_boost.rate_limiting.InMemoryBackend"
        ),
    },
}
```

---

## CLI reference

```
ninja-boost startproject <name>     Scaffold a complete new project
ninja-boost startapp <name>         Scaffold a new app in apps/<name>/
ninja-boost config                  Print a starter NINJA_BOOST settings block
```

**Scaffold a project:**
```bash
ninja-boost startproject bookstore
cd bookstore
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

**Scaffold an app:**
```bash
cd myproject
ninja-boost startapp products
# → apps/products/__init__.py
# → apps/products/routers.py       (AutoRouter with CRUD stubs)
# → apps/products/schemas.py       (Pydantic in/out schemas)
# → apps/products/services.py      (service class stub)
# → apps/products/models.py
# → apps/products/apps.py
# → apps/products/migrations/__init__.py
```

---

## Security considerations

1. **Replace `BearerTokenAuth` before going to production.** The default auth accepts the literal token `"demo"` and is intentionally insecure. Swap in a real JWT, session, or API-key authenticator.

2. **Set `ALLOWED_HOSTS`** in production settings.

3. **Protect the docs** with `NINJA_BOOST["DOCS"]["DISABLE_IN_PRODUCTION"] = True` or `REQUIRE_STAFF = True`.

4. **Use HTTPS in production.** Set `SECURE_SSL_REDIRECT = True` and configure TLS termination at the load balancer.

5. **Rate limit sensitive endpoints** (login, password reset, send-email) with tight limits like `"5/minute"`.

6. **Use `CacheBackend` with Redis** for rate limiting in multi-process deployments — `InMemoryBackend` is per-process.

7. **Pin your `SECRET_KEY`** and rotate it by deploying without old tokens being valid (implement token expiry).

---

## Performance notes

- **Pagination:** always uses `QuerySet.count()` + slice — two SQL queries maximum. Never calls `len()` on a QuerySet.
- **Rate limiting (InMemoryBackend):** O(n) sliding window cleanup — suitable for <1M unique rate-limit keys. For higher key counts, use `CacheBackend` with Redis (O(1) per request).
- **Event bus:** O(n) over registered handlers per event. Handler exceptions are swallowed. For hot paths, keep handler count <10 and handlers fast.
- **Context injection:** adds ~0.5µs overhead (one dict construction per request).
- **Caching:** `cache_response` uses MD5 to hash keys — negligible CPU cost.
- **Structured logging:** uses `contextvars` (single `ContextVar.get()` per log record) — faster than threadlocals.

---

## Troubleshooting & FAQ

**Q: My views are getting paginated but I don't want that on a specific route.**

```python
@router.post("/", response=UserOut, paginate=False)
def create_user(request, ctx, payload: UserCreate):
    ...
```

**Q: I'm getting `ImproperlyConfigured` on startup.**

If you set any of the four core keys (`AUTH`, `RESPONSE_WRAPPER`, `PAGINATION`, `DI`), you must set all four. Either provide all four or remove your partial `NINJA_BOOST` config entirely (defaults will kick in).

**Q: `ctx["user"]` is `None` even though I'm sending a valid token.**

Your auth class's `authenticate()` method returned `None`. Check that the token is valid and your auth class is configured in `NINJA_BOOST["AUTH"]`. Use `@router.get("/debug", auth=None)` temporarily to test without auth.

**Q: Rate limiting doesn't work across multiple gunicorn workers.**

Switch to `CacheBackend` — `InMemoryBackend` is process-local. Install Redis and set:
```python
NINJA_BOOST = {"RATE_LIMIT": {"BACKEND": "ninja_boost.rate_limiting.CacheBackend"}}
```

**Q: I need cursor-based pagination instead of page/size.**

Point `PAGINATION` at your custom decorator:
```python
NINJA_BOOST = {"PAGINATION": "myproject.pagination.cursor_paginate", ...}
```

**Q: Can I use ninja-boost alongside existing vanilla Django Ninja routers?**

Yes. `AutoRouter` and `Router` can be added to the same `NinjaAPI`/`AutoAPI` instance. Only `AutoRouter` routes get auto-wired features.

**Q: Can I use ninja-boost in an existing Django project that already has NinjaAPI?**

Yes. Swap `NinjaAPI` for `AutoAPI` in one place (urls.py). Existing routers are unaffected.

---

## Comparison table

| Feature | Django Ninja (bare) | django-ninja-boost |
|---------|--------------------|--------------------|
| Auto auth wiring | ❌ Manual per-route | ✅ Settings-driven |
| Response envelope | ❌ Manual | ✅ Automatic |
| Pagination | ❌ Manual 6+ lines | ✅ Automatic |
| Context injection | ❌ `request.auth` manually | ✅ `ctx["user"]`, `ctx["ip"]`, `ctx["trace_id"]` |
| Trace IDs | ❌ No built-in | ✅ `TracingMiddleware` |
| Rate limiting | ❌ Separate package | ✅ `@rate_limit("N/period")` |
| Permissions | ❌ Inline if-checks | ✅ `@require(IsStaff)` |
| Policies | ❌ Scattered per-view | ✅ Resource policy classes |
| Event hooks | ❌ No built-in | ✅ `event_bus.on("before_request")` |
| Plugin system | ❌ No built-in | ✅ `BoostPlugin` base class |
| DI container | ❌ No built-in | ✅ Service registry |
| Structured logs | ❌ Manual formatter | ✅ Auto-enriched JSON logs |
| Metrics | ❌ SDK-specific setup | ✅ Pluggable backends |
| Async views | ✅ Built-in | ✅ + auto-detected wrappers |
| Health checks | ❌ DIY | ✅ `/health/live` + `/health/ready` |
| Response caching | ❌ Manual | ✅ `@cache_response(ttl=60)` |
| API versioning | ❌ Manual URL routing | ✅ `VersionedRouter`, `versioned_api()` |
| Docs access control | ❌ No built-in | ✅ IP allowlist, staff-only |
| CLI scaffolding | ❌ No built-in | ✅ `ninja-boost startproject/startapp` |
| Zero breaking changes | N/A | ✅ Fully additive, opt-out per route |

---

## Changelog

### 0.2.0 (2026-02-24)

**New modules (11):**
- `events` — pub/sub event bus with sync + async handlers
- `plugins` — plugin base class and registry, auto-wired to events
- `rate_limiting` — `@rate_limit("N/period")` with InMemory + Cache backends
- `permissions` — declarative permission classes, `@require()` decorator
- `policies` — resource policy registry, `@policy()` decorator
- `services` — service DI container, `@inject_service()` decorator
- `logging_structured` — `StructuredJsonFormatter`, access log, context binding
- `metrics` — Prometheus / StatsD / Logging backends, `@track()` decorator
- `async_support` — auto-detected async DI, pagination, rate limit, permissions
- `lifecycle` — `LifecycleMiddleware` single-point lifecycle coordinator
- `health` — `/health/live` + `/health/ready` with custom checks
- `caching` — `@cache_response()` with Django cache backend integration
- `versioning` — `VersionedRouter`, `versioned_api()`, `@deprecated`, `@require_version`
- `docs` — `DocGuard`, `harden_docs()`, security scheme injection

**Updated modules:**
- `api` — fires plugin startup + docs hardening on init
- `router` — async-aware, global rate limit wiring
- `dependencies` — service registry enrichment, `before_request` event emission
- `middleware` — emits `after_response` event
- `exceptions` — emits `on_error` event, trace_id in logs
- `apps` — auto-loads plugins/policies/services, wires default event handlers
- `conf` — full settings reference, `get()` method for non-import keys
- `__init__` — exports all new public API

**Version bump:** `0.1.0` → `0.2.0`

### 0.1.0 (initial release)

- `AutoAPI`, `AutoRouter`, `inject_context`, `auto_paginate`
- `TracingMiddleware`, `register_exception_handlers`
- `BearerTokenAuth`, `wrap_response`
- `ninja-boost startproject/startapp/config` CLI

---

## Contributing

Contributions are welcome!

```bash
git clone https://github.com/bensylvenus/django-ninja-boost
cd django-ninja-boost
pip install -e ".[dev]"
pytest
```

Areas where help is appreciated:
- More metrics backends (Datadog, CloudWatch, OpenTelemetry)
- GraphQL support exploration
- More built-in permission classes
- Documentation improvements and recipes

Please open an issue before submitting large PRs to discuss the approach.

---

## License

MIT — see [LICENSE](LICENSE).
