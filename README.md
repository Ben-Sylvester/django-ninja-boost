# django-ninja-boost

**The automation layer Django Ninja was always missing.**  
Auto-wires authentication, response envelopes, pagination, request-context injection, and distributed tracing — configure once, write APIs forever.

[![PyPI version](https://img.shields.io/pypi/v/django-ninja-boost.svg)](https://pypi.org/project/django-ninja-boost/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Django 4.2+](https://img.shields.io/badge/django-4.2+-green.svg)](https://djangoproject.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://github.com/bensylvenus/django-ninja-boost/actions/workflows/test.yml/badge.svg)](https://github.com/bensylvenus/django-ninja-boost/actions)

---

## Table of Contents

- [What is this?](#what-is-this)
- [The problem it solves](#the-problem-it-solves)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [5-Minute Quick Start](#5-minute-quick-start)
- [Adding to an existing project](#adding-to-an-existing-project)
- [Complete project walkthrough](#complete-project-walkthrough)
- [Feature reference](#feature-reference)
  - [AutoAPI](#autoapi--response-envelope)
  - [AutoRouter](#autorouter--auth--di--pagination)
  - [Context injection (ctx)](#context-injection-ctx)
  - [Auto-pagination](#auto-pagination)
  - [Tracing middleware](#tracing-middleware)
  - [Exception handlers](#exception-handlers)
- [Configuration reference](#configuration-reference)
- [Per-route opt-out flags](#per-route-opt-out-flags)
- [Custom integrations](#custom-integrations)
  - [Custom auth (JWT)](#custom-auth-jwt)
  - [Django session auth](#django-session-auth)
  - [API key auth](#api-key-auth)
  - [Custom response envelope](#custom-response-envelope)
  - [Custom pagination (cursor-based)](#custom-pagination-cursor-based)
  - [Custom DI context](#custom-di-context)
- [Real-world patterns](#real-world-patterns)
  - [Role-based access control](#role-based-access-control)
  - [Multi-tenant APIs](#multi-tenant-apis)
  - [File uploads](#file-uploads)
  - [Multiple API versions](#multiple-api-versions)
  - [Background tasks](#background-tasks)
- [Testing](#testing)
- [Deployment](#deployment)
  - [Environment variables](#environment-variables)
  - [Production settings](#production-settings)
  - [Docker](#docker)
- [CLI reference](#cli-reference)
- [Security considerations](#security-considerations)
- [Performance notes](#performance-notes)
- [Troubleshooting & FAQ](#troubleshooting--faq)
- [How it relates to Django Ninja](#how-it-relates-to-django-ninja)
- [Comparison table](#comparison-table)
- [Project structure](#project-structure)
- [Contributing](#contributing)
- [Changelog](#changelog)
- [License](#license)

---

## What is this?

**django-ninja-boost** is an extension library that sits on top of [Django Ninja](https://django-ninja.dev/) and eliminates the repetitive boilerplate every team writes when building production APIs:

- It does **not** replace Django Ninja — it extends it with two drop-in subclasses
- Configure once in `settings.py` and every router inherits auth, pagination, and DI automatically
- Every existing Django Ninja feature (schemas, TestClient, OpenAPI docs, Router args) still works unchanged
- You can migrate one router at a time — your un-migrated routes keep working as normal

Think of it as the difference between vanilla Django and Django REST Framework — same foundation, dramatically less manual wiring.

---

## The problem it solves

Every endpoint in a vanilla Django Ninja project requires this same ceremony:

```python
# Repeated. On every. Single. Router. File.
from ninja import Router
from ninja.security import HttpBearer

class JWTAuth(HttpBearer):
    def authenticate(self, request, token):
        ...  # same code copied into every project

router = Router()

@router.get("/users", auth=JWTAuth(), response=list[UserOut])
def list_users(request):
    user  = request.auth                         # manually unpack auth
    ip    = request.META.get("REMOTE_ADDR")      # manually get IP
    qs    = User.objects.all()
    page  = int(request.GET.get("page", 1))      # manually paginate
    size  = int(request.GET.get("size", 20))
    start = (page - 1) * size
    data  = list(qs[start:start + size])
    total = qs.count()
    return {                                      # manually shape every response
        "ok":    True,
        "data":  data,
        "page":  page,
        "size":  size,
        "total": total,
    }
```

With `django-ninja-boost`, configure it once and write only this:

```python
from ninja_boost import AutoRouter

router = AutoRouter()

@router.get("/users", response=list[UserOut])
def list_users(request, ctx):
    return User.objects.all()
    # ↑ auth ✓  pagination ✓  response shape ✓  IP ✓  tracing ✓  all automatic
```

Same API. Same behaviour. Zero repetition.

---

## Prerequisites

Before installing, make sure you have:

- **Python 3.10 or higher** — check with `python --version`
- **Django 4.2 or higher** — check with `python -m django --version`
- **django-ninja 0.21.0 or higher** — check with `pip show django-ninja`
- **pydantic 2.2 or higher** — installed automatically with django-ninja

If you are new to Django Ninja, read their [5-minute tutorial](https://django-ninja.dev/tutorial/) first. `ninja_boost` builds directly on top of it and assumes you understand `NinjaAPI`, `Router`, and Schemas.

---

## Installation

```bash
pip install django-ninja django-ninja-boost
```

Both packages are needed. `django-ninja` is a peer dependency — `ninja_boost` extends it, not replaces it.

Verify the installation:

```bash
python -c "import ninja_boost; print(ninja_boost.__version__)"
# 0.1.0

ninja-boost --help
# usage: ninja-boost [-h] {startproject,startapp,config} ...
```

---

## 5-Minute Quick Start

The fastest way to see everything working:

```bash
# 1. Install
pip install django-ninja django-ninja-boost

# 2. Scaffold a complete project
ninja-boost startproject myapi

# 3. Install project dependencies
cd myapi && pip install -r requirements.txt

# 4. Run migrations (creates Django auth tables)
python manage.py migrate

# 5. Start the dev server
python manage.py runserver
```

Open your browser:

- **Interactive Swagger docs:** [http://localhost:8000/api/docs](http://localhost:8000/api/docs)
- **OpenAPI JSON:** [http://localhost:8000/api/openapi.json](http://localhost:8000/api/openapi.json)

Test with curl (the scaffolded project uses a demo bearer token):

```bash
# Without auth — returns 401
curl http://localhost:8000/api/users/

# With the demo token — returns paginated response
curl -H "Authorization: Bearer demo" http://localhost:8000/api/users/
# {"ok": true, "data": {"items": [], "page": 1, "size": 20, "total": 0, "pages": 1}}
```

Everything is working. Now scaffold your first real app:

```bash
ninja-boost startapp products
```

---

## Adding to an existing project

Already have a Django Ninja project? This is a **3-step migration**. None of your existing routes break — you can migrate one router at a time.

### Step 1 — Register in settings.py

```python
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    # ... your existing apps ...
    "ninja_boost",          # ← add
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # ... your existing middleware ...
    "ninja_boost.middleware.TracingMiddleware",   # ← add (optional, recommended)
]

# All four keys are optional — built-in defaults are used for anything omitted
NINJA_BOOST = {
    "AUTH":             "ninja_boost.integrations.BearerTokenAuth",  # replace with your real auth
    "RESPONSE_WRAPPER": "ninja_boost.responses.wrap_response",
    "PAGINATION":       "ninja_boost.pagination.auto_paginate",
    "DI":               "ninja_boost.dependencies.inject_context",
}
```

### Step 2 — Swap NinjaAPI → AutoAPI in urls.py

```python
# Before:
from ninja import NinjaAPI
api = NinjaAPI()

# After — one import, one class name:
from ninja_boost import AutoAPI
from ninja_boost.exceptions import register_exception_handlers

api = AutoAPI(title="My API", version="1.0")   # all NinjaAPI args still work
register_exception_handlers(api)

# Everything else stays the same:
from apps.users.routers import router as users_router
api.add_router("/users", users_router)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/",   api.urls),
]
```

### Step 3 — Swap Router → AutoRouter in your app files

```python
# Before:
from ninja import Router
router = Router(tags=["Users"])

# After:
from ninja_boost import AutoRouter
router = AutoRouter(tags=["Users"])

# Your routes stay the same — except they now receive ctx automatically:
@router.get("/", response=list[UserOut])
def list_users(request, ctx):     # ← add ctx as second argument
    return UserService.list_users()
```

That's it. Routers you haven't migrated yet continue working exactly as before.

---

## Complete project walkthrough

This section builds a real bookstore API end-to-end so you can see how all pieces fit together.

### Project layout

```
bookstore/
├── manage.py
├── requirements.txt
├── bookstore/              ← Django project package
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
└── apps/
    ├── __init__.py
    └── books/
        ├── __init__.py
        ├── apps.py
        ├── models.py
        ├── schemas.py      ← Pydantic input/output shapes
        ├── services.py     ← business logic (no HTTP here)
        ├── routers.py      ← HTTP route definitions
        └── migrations/
            └── __init__.py
```

### models.py

```python
from django.db import models

class Book(models.Model):
    title     = models.CharField(max_length=255)
    author    = models.CharField(max_length=255)
    isbn      = models.CharField(max_length=13, unique=True)
    price     = models.DecimalField(max_digits=8, decimal_places=2)
    published = models.DateField()
    in_stock  = models.BooleanField(default=True)

    class Meta:
        ordering = ["title"]
```

### schemas.py

Schemas define what goes in and what comes out of your API. Pure Pydantic — nothing boost-specific here.

```python
from ninja import Schema
from datetime import date
from decimal import Decimal
from typing import Optional

class BookOut(Schema):
    id:        int
    title:     str
    author:    str
    isbn:      str
    price:     Decimal
    published: date
    in_stock:  bool

class BookCreate(Schema):
    title:     str
    author:    str
    isbn:      str
    price:     Decimal
    published: date

class BookUpdate(Schema):
    title:    Optional[str]     = None
    author:   Optional[str]     = None
    price:    Optional[Decimal] = None
    in_stock: Optional[bool]    = None

class BookFilters(Schema):
    author:   Optional[str]  = None
    in_stock: Optional[bool] = None
```

### services.py

Services contain all business logic and database access. They have no knowledge of HTTP — easy to test, easy to reuse from CLI commands or background tasks.

```python
from django.shortcuts import get_object_or_404
from .models import Book
from .schemas import BookCreate, BookUpdate, BookOut, BookFilters

class BookService:

    @staticmethod
    def list_books(filters: BookFilters):
        """
        Return a filtered QuerySet.

        Returning a QuerySet (not list()) lets auto_paginate use efficient
        .count() + LIMIT/OFFSET instead of loading the whole table first.
        """
        qs = Book.objects.all()
        if filters.author:
            qs = qs.filter(author__icontains=filters.author)
        if filters.in_stock is not None:
            qs = qs.filter(in_stock=filters.in_stock)
        return qs

    @staticmethod
    def get_book(book_id: int) -> BookOut:
        book = get_object_or_404(Book, id=book_id)
        return BookOut.from_orm(book)

    @staticmethod
    def create_book(data: BookCreate) -> BookOut:
        book = Book.objects.create(**data.dict())
        return BookOut.from_orm(book)

    @staticmethod
    def update_book(book_id: int, data: BookUpdate) -> BookOut:
        book = get_object_or_404(Book, id=book_id)
        for field, value in data.dict(exclude_none=True).items():
            setattr(book, field, value)
        book.save()
        return BookOut.from_orm(book)

    @staticmethod
    def delete_book(book_id: int) -> None:
        get_object_or_404(Book, id=book_id).delete()
```

### routers.py

This is where `ninja_boost` shines — clean HTTP wiring with zero boilerplate:

```python
from ninja import Query
from ninja.errors import HttpError
from ninja_boost import AutoRouter
from .schemas import BookOut, BookCreate, BookUpdate, BookFilters
from .services import BookService

router = AutoRouter(tags=["Books"])


@router.get("/", response=list[BookOut])
def list_books(request, ctx, filters: BookFilters = Query(...)):
    """
    List all books with optional filters.

    Everything below is automatic — no code needed:
      - Auth enforced (from NINJA_BOOST["AUTH"])
      - ctx injected: ctx["user"], ctx["ip"], ctx["trace_id"]
      - Paginated: client sends ?page=2&size=10
      - Response wrapped: {"ok": true, "data": {"items": [...], ...}}
    """
    return BookService.list_books(filters)


@router.get("/{book_id}", response=BookOut, paginate=False)
def get_book(request, ctx, book_id: int):
    """Single object — paginate=False because we don't return a list."""
    return BookService.get_book(book_id)


@router.post("/", response=BookOut, paginate=False)
def create_book(request, ctx, payload: BookCreate):
    """ctx["user"] holds whatever your AUTH backend returned."""
    return BookService.create_book(payload)


@router.patch("/{book_id}", response=BookOut, paginate=False)
def update_book(request, ctx, book_id: int, payload: BookUpdate):
    """Partial update — only send the fields you want to change."""
    return BookService.update_book(book_id, payload)


@router.delete("/{book_id}", paginate=False)
def delete_book(request, ctx, book_id: int):
    BookService.delete_book(book_id)
    return None


@router.get("/featured", response=list[BookOut], auth=None)
def featured_books(request):
    """
    Public endpoint — auth=None disables authentication.
    inject=False is also an option if you don't need ctx here.
    """
    return Book.objects.filter(in_stock=True).order_by("-published")[:5]
```

### settings.py

```python
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = "your-secret-key-here"   # use env var in production
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "ninja_boost",
    "apps.books",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "ninja_boost.middleware.TracingMiddleware",
]

NINJA_BOOST = {
    "AUTH":             "bookstore.auth.JWTAuth",
    "RESPONSE_WRAPPER": "ninja_boost.responses.wrap_response",
    "PAGINATION":       "ninja_boost.pagination.auto_paginate",
    "DI":               "ninja_boost.dependencies.inject_context",
}

ROOT_URLCONF = "bookstore.urls"
DATABASES = {
    "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}
}
USE_TZ = True
```

### urls.py

```python
from django.contrib import admin
from django.urls import path
from ninja_boost import AutoAPI
from ninja_boost.exceptions import register_exception_handlers
from apps.books.routers import router as books_router

api = AutoAPI(
    title="Bookstore API",
    version="1.0",
    description="Sample API built with django-ninja-boost",
)
register_exception_handlers(api)
api.add_router("/books", books_router)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/",   api.urls),
]
```

### Making requests

```bash
# List all books (paginated, default page 1 size 20)
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/books/
# {"ok": true, "data": {"items": [...], "page": 1, "size": 20, "total": 47, "pages": 3}}

# Page 2, 5 items per page
curl -H "Authorization: Bearer <token>" "http://localhost:8000/api/books/?page=2&size=5"

# Filter by author
curl -H "Authorization: Bearer <token>" "http://localhost:8000/api/books/?author=tolkien"

# Get a single book
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/books/1
# {"ok": true, "data": {"id": 1, "title": "...", ...}}

# Create a book
curl -X POST \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{"title":"Dune","author":"Herbert","isbn":"9780441013593","price":12.99,"published":"1965-08-01"}' \
     http://localhost:8000/api/books/

# Public endpoint — no token needed
curl http://localhost:8000/api/books/featured

# Error response shape
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/books/9999
# {"ok": false, "error": "Not Found", "code": 404}
```

---

## Feature reference

### AutoAPI — response envelope

`AutoAPI` is a subclass of Django Ninja's `NinjaAPI`. It accepts every argument `NinjaAPI` accepts, and adds two automatic behaviours.

**1. Default authentication** — reads `NINJA_BOOST["AUTH"]`, instantiates it, and sets it as the API-wide default. Individual routes can override this with `auth=MyAuth()` or `auth=None`.

**2. Response envelope** — every successful response is wrapped automatically:

```json
{"ok": true, "data": <your return value>}
```

Error responses from `register_exception_handlers` use the same outer shape with `"ok": false`:

```json
{"ok": false, "error": "Item not found", "code": 404}
```

`AutoAPI` detects pre-wrapped responses by checking for the `"ok"` key and skips re-wrapping, so error and success responses are always clean — no double-wrapping.

**All NinjaAPI constructor arguments work unchanged:**

```python
api = AutoAPI(
    title="My API",
    version="2.0",
    description="Shown in Swagger UI",
    docs_url="/docs",
    openapi_url="/openapi.json",
    urls_namespace="api",       # for Django URL reversing
    csrf=True,                  # enable CSRF for cookie-based auth
    auth=MyCustomAuth(),        # override the NINJA_BOOST default globally
)
```

---

### AutoRouter — auth + DI + pagination

`AutoRouter` is a subclass of Django Ninja's `Router`. It accepts every argument `Router` accepts, and automatically applies three behaviours to every route registered through it.

**Authentication** — reads `NINJA_BOOST["AUTH"]`, instantiates it, and passes it to every operation. Override per-route with `auth=MyAuth()` or disable with `auth=None`.

**Dependency injection** — wraps each view function with the DI decorator before registering, so every view receives `ctx` as its second argument automatically.

**Pagination** — wraps each view function with the pagination decorator, so any view that returns a list or QuerySet is automatically paginated.

```python
from ninja_boost import AutoRouter

router = AutoRouter(
    tags=["Books"],      # Swagger grouping tag — same as Router
)
```

---

### Context injection (ctx)

Every view registered on an `AutoRouter` receives a `ctx` dict as its second argument. No decorator is needed — it is injected by the DI layer before your function is called.

```python
@router.get("/profile")
def profile(request, ctx):
    user     = ctx["user"]      # whatever your AUTH backend's .authenticate() returned
    ip       = ctx["ip"]        # real client IP, honours X-Forwarded-For
    trace_id = ctx["trace_id"]  # UUID hex from TracingMiddleware, or None
```

**What `ctx["user"]` contains** is entirely determined by your AUTH backend. If your `HttpBearer.authenticate()` returns a JWT payload dict, `ctx["user"]` is that dict. If it returns a Django `User` object, `ctx["user"]` is that object. You control this completely.

**`ctx["ip"]` resolution** reads `HTTP_X_FORWARDED_FOR` first (taking the leftmost address — the original client) and falls back to `REMOTE_ADDR`. This correctly handles proxies and load balancers.

**`ctx["trace_id"]`** contains the 32-character hex UUID generated by `TracingMiddleware`. If the middleware is not installed, this value is `None`.

**Opt out on specific routes** with `inject=False`:

```python
@router.get("/ping", auth=None, inject=False, paginate=False)
def ping(request):
    # No ctx parameter — use for simple health-check style endpoints
    return {"pong": True}
```

---

### Auto-pagination

`auto_paginate` is applied to every route on an `AutoRouter`. If your view returns a list or Django QuerySet, the decorator slices it and returns a pagination envelope.

**Return a QuerySet for best performance:**

```python
@router.get("/books", response=list[BookOut])
def list_books(request, ctx):
    return Book.objects.filter(in_stock=True)  # ← QuerySet, not list()
```

The paginator calls `.count()` (one `COUNT(*)` SQL query) then applies a LIMIT/OFFSET slice (one `SELECT` SQL query). Total cost: 2 queries regardless of how many rows exist. Never loads the full table.

**Pagination query parameters:**

| Parameter | Type | Default | Maximum | Description |
|-----------|------|---------|---------|-------------|
| `?page`   | int  | `1`     | —       | Page number, 1-based |
| `?size`   | int  | `20`    | `200`   | Items per page |

**Paginated response shape:**

```json
{
  "ok": true,
  "data": {
    "items": [ {...}, {...} ],
    "page":  2,
    "size":  10,
    "total": 142,
    "pages": 15
  }
}
```

**Opt out per route** — use `paginate=False` for single objects, create, update, and delete operations:

```python
@router.get("/{id}",   response=BookOut,  paginate=False)  # single object
@router.post("/",      response=BookOut,  paginate=False)  # create
@router.patch("/{id}", response=BookOut,  paginate=False)  # update
@router.delete("/{id}",                  paginate=False)  # delete
```

Invalid inputs are handled gracefully — `?page=abc` silently defaults to `1`.

---

### Tracing middleware

`TracingMiddleware` runs before every request and attaches a UUID trace ID to it.

**Enable in settings.py:**

```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # ... other middleware ...
    "ninja_boost.middleware.TracingMiddleware",
]
```

**What you get:**

| Where | How to access | Value |
|-------|--------------|-------|
| Inside any view | `request.trace_id` | 32-char hex UUID |
| Inside AutoRouter views | `ctx["trace_id"]` | same value |
| In the HTTP response | `X-Trace-Id` header | same value |
| In Django logs | automatic `DEBUG` log line | `METHOD /path [trace=...]` |

**Use in structured logging:**

```python
import logging
logger = logging.getLogger(__name__)

@router.get("/orders/{id}")
def get_order(request, ctx, id: int):
    logger.info("Fetching order %s", id, extra={"trace_id": ctx["trace_id"]})
    return OrderService.get(id)
```

**Correlate across microservices** — forward the trace ID to downstream calls:

```python
import httpx

@router.post("/checkout")
def checkout(request, ctx, payload: CheckoutRequest):
    response = httpx.post(
        "https://payments.internal/charge",
        json=payload.dict(),
        headers={"X-Trace-Id": ctx["trace_id"]},
    )
    return response.json()
```

---

### Exception handlers

`register_exception_handlers(api)` registers two handlers that return errors in the standard envelope format.

```python
from ninja_boost import AutoAPI
from ninja_boost.exceptions import register_exception_handlers

api = AutoAPI()
register_exception_handlers(api)
```

**Handler 1 — HttpError** (from `ninja.errors`):

```python
from ninja.errors import HttpError

def get_book(book_id: int):
    book = Book.objects.filter(id=book_id).first()
    if not book:
        raise HttpError(404, "Book not found")
    return book

# Client receives:
# {"ok": false, "error": "Book not found", "code": 404}
```

**Common HTTP codes to use with `HttpError`:**

| Code | Meaning | When to use |
|------|---------|-------------|
| 400  | Bad Request | Invalid input not caught by schema |
| 401  | Unauthorized | User must authenticate |
| 403  | Forbidden | User lacks permission |
| 404  | Not Found | Resource doesn't exist |
| 409  | Conflict | Duplicate, locked resource |
| 422  | Unprocessable | Passes validation, fails business rules |
| 429  | Too Many Requests | Rate limit exceeded |

**Handler 2 — generic Exception** — any unhandled exception returns a clean 500 to the client without leaking stack traces. The full traceback still appears in server logs.

```json
{"ok": false, "error": "Internal server error.", "code": 500}
```

**Register additional custom exception types** after the built-in handlers:

```python
register_exception_handlers(api)   # built-in handlers first

@api.exception_handler(InsufficientStockError)
def handle_stock(request, exc):
    return api.create_response(
        request,
        {"ok": False, "error": "Not enough stock.", "code": 409},
        status=409,
    )
```

---

## Configuration reference

All configuration lives in a single `NINJA_BOOST` dict in `settings.py`. Every key is optional — sensible defaults are used for any key you omit.

```python
# settings.py
NINJA_BOOST = {
    # Dotted path to an HttpBearer subclass (or compatible auth class)
    "AUTH": "myproject.auth.JWTAuth",

    # Dotted path to a callable(data: Any) -> dict
    "RESPONSE_WRAPPER": "ninja_boost.responses.wrap_response",

    # Dotted path to a view-function decorator for pagination
    "PAGINATION": "ninja_boost.pagination.auto_paginate",

    # Dotted path to a view-function decorator for context injection
    "DI": "ninja_boost.dependencies.inject_context",
}
```

| Key | Default | Description |
|-----|---------|-------------|
| `AUTH` | `ninja_boost.integrations.BearerTokenAuth` | Auth class. Instantiated per-router. Must implement the Django Ninja auth protocol. |
| `RESPONSE_WRAPPER` | `ninja_boost.responses.wrap_response` | Callable wrapping success response data. Signature: `(data: Any) -> dict`. |
| `PAGINATION` | `ninja_boost.pagination.auto_paginate` | Decorator applied to view functions that return lists or QuerySets. |
| `DI` | `ninja_boost.dependencies.inject_context` | Decorator applied to view functions to inject the context dict. |

**Use all defaults** (great for prototyping — don't include `NINJA_BOOST` in settings at all):

```python
# settings.py — omit NINJA_BOOST entirely, or use an empty dict
```

**Override only the auth** and keep everything else as defaults:

```python
NINJA_BOOST = {
    "AUTH": "myproject.auth.JWTAuth",
}
```

All four default values are listed in `ninja_boost/conf.py` and are always used as fallbacks.

---

## Per-route opt-out flags

These keyword arguments are consumed by `AutoRouter` and never passed to Django Ninja. They let you bypass specific behaviours for individual routes.

```python
@router.get(
    "/path",
    auth=None,          # disable auth entirely — public endpoint
    inject=False,       # don't inject ctx — view signature: (request, ...)
    paginate=False,     # don't paginate — return raw value
)
def my_view(request):
    ...
```

| Flag | Type | Default | Effect |
|------|------|---------|--------|
| `auth=None` | `None` | — | Disables authentication — public endpoint |
| `auth=MyAuth()` | instance | — | Overrides the global auth for this route only |
| `inject=False` | bool | `True` | View receives only `(request, ...)` — no `ctx` |
| `paginate=False` | bool | `True` | Returns raw return value — no pagination envelope |

**Common patterns:**

```python
# Health check — open, no ctx, no pagination
@router.get("/health", auth=None, inject=False, paginate=False)
def health(request):
    return {"status": "ok"}

# Single object — auth and ctx, but no pagination
@router.get("/{id}", response=ItemOut, paginate=False)
def get_item(request, ctx, id: int):
    return ItemService.get(id)

# Admin-only route with a different auth class
@router.delete("/{id}", auth=AdminAuth(), paginate=False)
def admin_delete(request, ctx, id: int):
    ...
```

---

## Custom integrations

### Custom auth (JWT)

The most common production pattern. Replace the demo auth with a real JWT validator:

```bash
pip install PyJWT
```

```python
# myproject/auth.py
import jwt
from ninja.security import HttpBearer
from django.conf import settings
from django.contrib.auth import get_user_model

User = get_user_model()

class JWTAuth(HttpBearer):
    def authenticate(self, request, token: str):
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return None    # expired token → 401
        except jwt.DecodeError:
            return None    # malformed token → 401

        try:
            user = User.objects.get(id=payload["user_id"])
        except User.DoesNotExist:
            return None

        # This return value becomes ctx["user"] in all your views
        return {
            "id":       user.id,
            "username": user.username,
            "email":    user.email,
            "is_staff": user.is_staff,
        }
```

```python
# settings.py
NINJA_BOOST = {
    "AUTH": "myproject.auth.JWTAuth",
}
```

---

### Django session auth

For browser-based SPAs using Django's built-in sessions:

```python
# settings.py — use Django Ninja's built-in session auth
NINJA_BOOST = {
    "AUTH": "ninja.security.django_auth",
}

# Also enable CSRF on AutoAPI for session auth:
# api = AutoAPI(csrf=True)
```

---

### API key auth

For machine-to-machine (M2M) or third-party integrations:

```python
# myproject/auth.py
from ninja.security import APIKeyHeader
from myproject.models import APIKey

class APIKeyAuth(APIKeyHeader):
    param_name = "X-API-Key"

    def authenticate(self, request, key: str):
        try:
            api_key = APIKey.objects.select_related("owner").get(
                key=key, is_active=True
            )
            return {"owner": api_key.owner, "scope": api_key.scope}
        except APIKey.DoesNotExist:
            return None
```

---

### Custom response envelope

Replace `{"ok": True, "data": ...}` with your own shape:

```python
# myproject/responses.py
from typing import Any
from datetime import datetime, timezone

def versioned_envelope(data: Any) -> dict:
    return {
        "success":   True,
        "payload":   data,
        "api":       "v2",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
```

```python
NINJA_BOOST = {
    "RESPONSE_WRAPPER": "myproject.responses.versioned_envelope",
}
```

---

### Custom pagination (cursor-based)

For tables with millions of rows where offset pagination becomes slow:

```python
# myproject/pagination.py
import base64
from functools import wraps

def cursor_paginate(func):
    """Cursor-based pagination — more efficient than offset for large datasets."""
    @wraps(func)
    def wrapper(request, *args, **kwargs):
        result = func(request, *args, **kwargs)

        if result is None or isinstance(result, dict):
            return result   # single object — pass through

        size       = max(1, min(200, int(request.GET.get("size", 20))))
        cursor_raw = request.GET.get("cursor")
        after_id   = None

        if cursor_raw:
            try:
                after_id = int(base64.b64decode(cursor_raw).decode())
            except Exception:
                pass

        if after_id and hasattr(result, "filter"):
            result = result.filter(id__gt=after_id)

        page_items = list(result[:size + 1])
        has_next   = len(page_items) > size
        items      = page_items[:size]

        next_cursor = None
        if has_next and items and hasattr(items[-1], "id"):
            next_cursor = base64.b64encode(str(items[-1].id).encode()).decode()

        return {"items": items, "next_cursor": next_cursor, "has_next": has_next, "size": size}

    return wrapper
```

```python
NINJA_BOOST = {
    "PAGINATION": "myproject.pagination.cursor_paginate",
}
```

---

### Custom DI context

Add tenant, permissions, or feature flags to the context:

```python
# myproject/dependencies.py
from functools import wraps

def inject_rich_context(func):
    @wraps(func)
    def wrapper(request, *args, **kwargs):
        user = getattr(request, "auth", None)

        host      = request.get_host()
        tenant    = host.split(".")[0] if "." in host else "default"

        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        ip  = xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "")

        ctx = {
            "user":     user,
            "ip":       ip,
            "trace_id": getattr(request, "trace_id", None),
            "tenant":   tenant,
        }
        return func(request, ctx, *args, **kwargs)
    return wrapper
```

```python
NINJA_BOOST = {
    "DI": "myproject.dependencies.inject_rich_context",
}
```

---

## Real-world patterns

### Role-based access control

```python
# myproject/guards.py
from ninja.errors import HttpError

def require_staff(ctx: dict):
    if not ctx["user"].get("is_staff"):
        raise HttpError(403, "Staff access required.")

def require_permission(ctx: dict, codename: str):
    perms = ctx["user"].get("permissions", [])
    if codename not in perms:
        raise HttpError(403, f"Permission '{codename}' required.")
```

```python
# apps/books/routers.py
from myproject.guards import require_staff, require_permission

@router.post("/", response=BookOut, paginate=False)
def create_book(request, ctx, payload: BookCreate):
    require_permission(ctx, "books.add_book")   # ← raises 403 if not permitted
    return BookService.create_book(payload)

@router.delete("/{id}", paginate=False)
def delete_book(request, ctx, id: int):
    require_staff(ctx)
    BookService.delete_book(id)
    return None
```

---

### Multi-tenant APIs

Route requests to the correct data partition based on the tenant:

```python
@router.get("/", response=list[OrderOut])
def list_orders(request, ctx):
    # ctx["tenant"] from a custom DI decorator (see Custom DI context above)
    return Order.objects.filter(tenant=ctx["tenant"])
```

---

### File uploads

Django Ninja handles file uploads natively — no changes needed for boost:

```python
from ninja import File
from ninja.files import UploadedFile

@router.post("/cover", paginate=False)
def upload_cover(request, ctx, book_id: int, file: UploadedFile = File(...)):
    if file.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HttpError(400, "Only JPEG, PNG, and WebP images are accepted.")
    path = BookService.save_cover(book_id, file)
    return {"cover_url": path}
```

---

### Multiple API versions

Run v1 and v2 simultaneously:

```python
# urls.py
from ninja_boost import AutoAPI
from ninja_boost.exceptions import register_exception_handlers

api_v1 = AutoAPI(title="API v1", version="1.0", urls_namespace="api_v1")
register_exception_handlers(api_v1)
api_v1.add_router("/books", books_router_v1)

api_v2 = AutoAPI(title="API v2", version="2.0", urls_namespace="api_v2")
register_exception_handlers(api_v2)
api_v2.add_router("/books", books_router_v2)

urlpatterns = [
    path("api/v1/", api_v1.urls),
    path("api/v2/", api_v2.urls),
]
```

---

### Background tasks

Works alongside Celery or Django-Q without any conflicts:

```python
# tasks.py
from celery import shared_task

@shared_task
def process_import(file_path: str, user_id: int):
    BookService.bulk_import(file_path, imported_by=user_id)
```

```python
# routers.py
@router.post("/import", paginate=False)
def start_import(request, ctx, file: UploadedFile = File(...)):
    path = save_temp_file(file)
    task = process_import.delay(path, ctx["user"]["id"])
    return {"task_id": task.id, "status": "queued"}
```

---

## Testing

### Setup

```bash
pip install pytest pytest-django
```

```ini
# pytest.ini
[pytest]
DJANGO_SETTINGS_MODULE = myproject.settings
```

### Testing service layer

Services are plain Python — test them directly without HTTP overhead:

```python
# tests/test_book_service.py
import pytest
from django.test import TestCase
from apps.books.services import BookService
from apps.books.schemas import BookCreate
from apps.books.models import Book

class TestBookService(TestCase):

    def setUp(self):
        Book.objects.create(
            title="Dune", author="Herbert", isbn="9780441013593",
            price=12.99, published="1965-08-01"
        )

    def test_list_returns_queryset(self):
        from apps.books.schemas import BookFilters
        assert BookService.list_books(BookFilters()).count() == 1

    def test_filter_by_author(self):
        from apps.books.schemas import BookFilters
        assert BookService.list_books(BookFilters(author="Tolkien")).count() == 0

    def test_create_book(self):
        data = BookCreate(title="1984", author="Orwell", isbn="9780451524935",
                          price=9.99, published="1949-06-08")
        result = BookService.create_book(data)
        assert result.title == "1984"
        assert Book.objects.count() == 2
```

### Testing API endpoints

Django Ninja's `TestClient` makes HTTP calls without running a server:

```python
# tests/test_book_api.py
import pytest
from ninja.testing import TestClient
from apps.books.routers import router

client = TestClient(router)

class TestBookAPI:

    def test_requires_auth(self, db):
        response = client.get("/")
        assert response.status_code == 401

    def test_list_books(self, db):
        response = client.get("/", headers={"Authorization": "Bearer demo"})
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "items" in data["data"]

    def test_404_shape(self, db):
        response = client.get("/9999", headers={"Authorization": "Bearer demo"})
        assert response.status_code == 404
        body = response.json()
        assert body["ok"] is False
        assert "error" in body

    def test_create_book(self, db):
        payload = {
            "title": "1984", "author": "Orwell", "isbn": "9780451524935",
            "price": "9.99", "published": "1949-06-08"
        }
        response = client.post("/", json=payload,
                               headers={"Authorization": "Bearer demo"})
        assert response.status_code == 200
        assert response.json()["data"]["title"] == "1984"
```

### Testing pagination

```python
# tests/test_pagination.py
from unittest.mock import MagicMock
from ninja_boost.pagination import auto_paginate

def make_request(page=1, size=20):
    r = MagicMock()
    r.GET = {"page": str(page), "size": str(size)}
    return r

def test_paginates_list():
    @auto_paginate
    def view(request): return list(range(50))

    result = view(make_request(page=2, size=10))
    assert result["items"] == list(range(10, 20))
    assert result["total"] == 50
    assert result["pages"] == 5

def test_queryset_uses_count_not_len():
    """Verify .count() is used — never len() which loads the whole table."""
    from ninja_boost.pagination import _is_queryset

    mock_qs = MagicMock()
    mock_qs.count.return_value = 1000
    mock_qs.__getitem__ = lambda self, sl: []
    mock_qs.filter = MagicMock()
    mock_qs.values = MagicMock()
    assert _is_queryset(mock_qs)

    @auto_paginate
    def view(request): return mock_qs

    view(make_request())
    mock_qs.count.assert_called_once()   # must use .count()
```

### Overriding NINJA_BOOST in tests

```python
from django.test import override_settings
from ninja_boost.conf import boost_settings

def test_custom_auth():
    with override_settings(NINJA_BOOST={"AUTH": "tests.auth.MockAuth"}):
        boost_settings.reload()   # clear the import cache after override
        assert boost_settings.AUTH.__name__ == "MockAuth"
    boost_settings.reload()       # restore defaults after the test
```

---

## Deployment

### Environment variables

Never put secrets in `settings.py`. Use environment variables:

```bash
pip install django-environ
```

```python
# settings.py
import environ

env = environ.Env(DEBUG=(bool, False))
environ.Env.read_env(".env")

SECRET_KEY   = env("SECRET_KEY")
DEBUG        = env("DEBUG")
DATABASES    = {"default": env.db()}
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")
```

```bash
# .env  ← never commit this file
SECRET_KEY=your-very-long-random-secret-key
DEBUG=False
DATABASE_URL=postgres://user:pass@localhost/dbname
ALLOWED_HOSTS=api.yourdomain.com
```

Generate a new secret key:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### Production settings

```python
# settings/production.py
from .base import *

DEBUG        = False
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")
SECRET_KEY   = env("SECRET_KEY")

DATABASES = {
    "default": {
        "ENGINE":   "django.db.backends.postgresql",
        "NAME":     env("DB_NAME"),
        "USER":     env("DB_USER"),
        "PASSWORD": env("DB_PASSWORD"),
        "HOST":     env("DB_HOST", default="localhost"),
        "PORT":     env("DB_PORT", default="5432"),
    }
}

# HTTPS
SECURE_SSL_REDIRECT            = True
SESSION_COOKIE_SECURE          = True
CSRF_COOKIE_SECURE             = True
SECURE_HSTS_SECONDS            = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True

# Structured logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}
```

### Docker

```dockerfile
# Dockerfile
FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN python manage.py collectstatic --no-input

EXPOSE 8000
CMD ["gunicorn", "myproject.wsgi:application", \
     "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "120"]
```

```yaml
# docker-compose.yml
version: "3.9"
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB:       myapi
      POSTGRES_USER:     myapi
      POSTGRES_PASSWORD: secret
    volumes:
      - postgres_data:/var/lib/postgresql/data

  web:
    build: .
    ports:
      - "8000:8000"
    environment:
      SECRET_KEY:   your-secret-key
      DATABASE_URL: postgres://myapi:secret@db/myapi
      DEBUG:        "False"
    depends_on:
      - db
    command: >
      sh -c "python manage.py migrate &&
             gunicorn myproject.wsgi:application --bind 0.0.0.0:8000"

volumes:
  postgres_data:
```

```bash
docker-compose up --build
```

---

## CLI reference

The `ninja-boost` CLI is installed automatically with the package.

### `ninja-boost startproject <name>`

Scaffolds a complete, ready-to-run Django project:

```bash
ninja-boost startproject bookstore
cd bookstore
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

**Generated structure:**

```
bookstore/
├── manage.py
├── requirements.txt
├── pytest.ini
├── apps/
│   └── __init__.py
└── bookstore/
    ├── __init__.py
    ├── settings.py      # NINJA_BOOST pre-configured with defaults
    ├── urls.py          # AutoAPI + register_exception_handlers wired
    ├── wsgi.py
    └── asgi.py
```

---

### `ninja-boost startapp <name>`

Scaffolds a new app inside `apps/<name>/`:

```bash
ninja-boost startapp products
```

**Generated structure:**

```
apps/
  products/
    __init__.py
    apps.py           # Django AppConfig
    models.py         # empty scaffold
    admin.py          # empty scaffold
    schemas.py        # ProductOut, ProductCreate, ProductUpdate
    services.py       # ProductService with list/get/create stubs
    routers.py        # AutoRouter with routes already wired to services
    migrations/
      __init__.py
```

**After `startapp`, do these three things:**

```python
# 1. settings.py
INSTALLED_APPS += ["apps.products"]

# 2. urls.py
from apps.products.routers import router as products_router
api.add_router("/products", products_router)
```

```bash
# 3. Shell
python manage.py makemigrations products
python manage.py migrate
```

---

### `ninja-boost config`

Prints a starter `NINJA_BOOST` settings block to copy into your `settings.py`:

```bash
ninja-boost config
```

---

## Security considerations

### Replace the demo auth before going live

`BearerTokenAuth` accepts the literal string `"demo"`. It exists for local development only. Always configure a real auth backend before any deployment:

```python
NINJA_BOOST = {
    "AUTH": "myproject.auth.JWTAuth",   # your real implementation
}
```

### Secret key management

- Never commit `SECRET_KEY` to version control
- Use a different `SECRET_KEY` in each environment (local, staging, production)
- Rotate the key periodically; existing sessions will be invalidated

### X-Forwarded-For trust

`inject_context` reads `X-Forwarded-For` to determine the real client IP. If your server is directly on the internet (not behind a trusted proxy), this header can be spoofed. Write a custom DI function that reads only `REMOTE_ADDR`:

```python
# myproject/dependencies.py
def inject_context_direct_ip(func):
    """For servers not behind a proxy — ignores X-Forwarded-For."""
    @wraps(func)
    def wrapper(request, *args, **kwargs):
        ctx = {
            "user":     getattr(request, "auth", None),
            "ip":       request.META.get("REMOTE_ADDR", ""),   # no XFF
            "trace_id": getattr(request, "trace_id", None),
        }
        return func(request, ctx, *args, **kwargs)
    return wrapper
```

### Rate limiting

`ninja_boost` does not include rate limiting. Add it at the proxy layer (nginx, Cloudflare) or with a Django package:

```bash
pip install django-ratelimit
```

```python
from django_ratelimit.decorators import ratelimit

@ratelimit(key="ip", rate="100/h", block=True)
@router.get("/search")
def search(request, ctx, q: str):
    ...
```

---

## Performance notes

### Always return a QuerySet from list endpoints

```python
# ✅ Two SQL queries regardless of table size
@router.get("/books")
def list_books(request, ctx):
    return Book.objects.filter(in_stock=True)   # returns QuerySet

# ❌ Loads entire table into memory before paginating
@router.get("/books")
def list_books(request, ctx):
    return list(Book.objects.filter(in_stock=True))   # returns list
```

### Use select_related / prefetch_related

```python
class OrderService:
    @staticmethod
    def list_orders():
        return (
            Order.objects
            .select_related("customer", "shipping_address")
            .prefetch_related("items__product")
            .filter(status="active")
        )
```

### BoostSettings caches resolved classes

`NINJA_BOOST` values are resolved once via `import_string` and cached. There is no per-request overhead from the settings proxy.

### Keep DI decorators cheap

The DI context decorator runs on every authenticated request. Avoid database queries inside it unless absolutely necessary. Fetch permissions lazily inside views that need them, or cache them on the request object.

---

## Troubleshooting & FAQ

**Q: `ImproperlyConfigured: [ninja_boost] NINJA_BOOST settings is missing keys`**

You have a partial `NINJA_BOOST` dict that is missing one or more of the four required keys. Either remove the dict entirely (all defaults are used), or include all four keys. Run `ninja-boost config` to see the full block.

---

**Q: My views aren't receiving `ctx` — I get a `TypeError` about unexpected arguments**

Your router must be `AutoRouter`, not the vanilla `Router`:

```python
# Wrong:
from ninja import Router
router = Router()

# Correct:
from ninja_boost import AutoRouter
router = AutoRouter()
```

---

**Q: I'm getting 401 on every request even when I send a token**

The default `BearerTokenAuth` only accepts the literal string `"demo"`. Test with:

```bash
curl -H "Authorization: Bearer demo" http://localhost:8000/api/your-endpoint/
```

In production, point `NINJA_BOOST["AUTH"]` at your real auth class.

---

**Q: My paginated endpoint returns a single object instead of a pagination envelope**

You returned a dict instead of a list or QuerySet. `auto_paginate` passes dicts through untouched. Fix your service:

```python
# Wrong — returns a dict
def list_books(): return {"books": [...]}

# Correct — returns a QuerySet
def list_books(): return Book.objects.all()

# Also correct — returns a list
def list_books(): return [book1, book2, book3]
```

---

**Q: How do I make a completely public endpoint?**

Use `auth=None` on the route:

```python
@router.get("/public", response=list[ItemOut], auth=None)
def public_items(request):
    return Item.objects.filter(featured=True)
```

Note: `ctx["user"]` will be `None` on public endpoints, but `ctx` is still injected if `inject=True` (the default). Use `inject=False` if you don't need ctx at all.

---

**Q: Can I use `ninja_boost` with `django-ninja-extra` (class-based views)?**

Yes. They are fully compatible. `AutoAPI` can host controllers from `django-ninja-extra` alongside function-based `AutoRouter` routes.

---

**Q: Does `ninja_boost` support async views?**

The current `inject_context` and `auto_paginate` decorators are synchronous. They wrap sync view functions correctly. Async view support is planned for a future release.

---

**Q: Will error responses get double-wrapped by AutoAPI?**

No. `AutoAPI.create_response` checks whether the data already contains an `"ok"` key. If it does, it skips the `wrap_response` call. Error handlers and success responses are always clean.

---

**Q: I changed `NINJA_BOOST` in a test but the old values are still being used**

The settings proxy caches resolved classes. Call `boost_settings.reload()` after changing settings in a test:

```python
from ninja_boost.conf import boost_settings
from django.test import override_settings

with override_settings(NINJA_BOOST={"AUTH": "tests.auth.MockAuth"}):
    boost_settings.reload()
    # test your code here
boost_settings.reload()   # restore defaults
```

---

**Q: How do I bypass the response envelope for one specific endpoint?**

Return a Django `HttpResponse` directly — it bypasses `AutoAPI.create_response` entirely:

```python
from django.http import JsonResponse

@router.get("/raw", auth=None, inject=False, paginate=False)
def raw(request):
    return JsonResponse({"custom": "shape", "no": "envelope"})
```

---

## How it relates to Django Ninja

`django-ninja-boost` does not fork or patch Django Ninja. It uses standard Python subclassing:

```
pip install django-ninja          ← upstream, untouched, receives updates normally
    NinjaAPI  ←──── AutoAPI subclasses this      (adds: default auth, response envelope)
    Router    ←──── AutoRouter subclasses this   (adds: per-operation auth, DI, pagination)
    Schema          unchanged — use as normal
    HttpBearer      unchanged — subclass for custom auth

pip install django-ninja-boost    ← our automation layer
    AutoAPI         + default auth, response envelope
    AutoRouter      + per-operation auth, DI, pagination
    inject_context  request context injection
    auto_paginate   transparent list/QuerySet pagination
    wrap_response   standard {"ok": true, "data": ...} envelope
    TracingMiddleware  UUID trace IDs on every request
```

When Django Ninja releases a new version with new features or bug fixes, you get those immediately — there is no compatibility lag from `ninja_boost`.

---

## Comparison table

### vs vanilla Django Ninja

| Task | Vanilla Django Ninja | With ninja_boost |
|------|---------------------|-----------------|
| Add auth to a route | `auth=JWTAuth()` on every `@router.get` | Once in `NINJA_BOOST["AUTH"]` |
| Consistent response shape | Write `{"ok": True, "data": ...}` in every view | Automatic |
| Paginate a QuerySet | ~15 lines of boilerplate per endpoint | Return the QuerySet |
| Access authenticated user | `request.auth` everywhere | `ctx["user"]` |
| Get client IP (proxy-aware) | Custom code per endpoint | `ctx["ip"]` |
| Per-request trace ID | Build custom middleware | `TracingMiddleware` + `ctx["trace_id"]` |
| Standard error shape | Write custom exception handlers per project | `register_exception_handlers(api)` |
| Catch unhandled 500s cleanly | Manual try/except or middleware | Included in `register_exception_handlers` |

### vs django-ninja-extra

[`django-ninja-extra`](https://pypi.org/project/django-ninja-extra/) and `django-ninja-boost` solve different problems and are fully compatible with each other.

| | `django-ninja-extra` | `django-ninja-boost` |
|-|----------------------|----------------------|
| Programming model | Class-based controllers | Function-based routes |
| Dependency injection | Constructor injection via `injector` lib | Request context dict (`ctx`) |
| Auth wiring | Per-controller decorator | Settings-driven, zero decorator |
| Response envelope | Manual | Automatic |
| Pagination | Manual | Automatic |
| Distributed tracing | Not included | `TracingMiddleware` |
| Scaffolding CLI | Not included | `ninja-boost startproject/startapp` |

---

## Project structure

```
django-ninja-boost/
├── src/
│   └── ninja_boost/
│       ├── __init__.py        public API surface
│       ├── api.py             AutoAPI subclass
│       ├── apps.py            Django AppConfig + startup validation
│       ├── cli.py             ninja-boost CLI
│       ├── conf.py            lazy BoostSettings proxy with defaults
│       ├── dependencies.py    inject_context decorator
│       ├── exceptions.py      register_exception_handlers
│       ├── integrations.py    BearerTokenAuth (demo, replace in production)
│       ├── middleware.py      TracingMiddleware
│       ├── pagination.py      auto_paginate decorator
│       ├── py.typed           PEP 561 marker for type checkers
│       ├── responses.py       wrap_response function
│       └── router.py          AutoRouter subclass
├── template/                  starter project (used by CLI)
├── tests/
│   ├── conftest.py
│   └── test_core.py
├── .github/workflows/
│   └── test.yml               CI: Python 3.10-3.12 × Django 4.2-5.0
├── pyproject.toml
├── MANIFEST.in
├── LICENSE
└── README.md
```

---

## Contributing

Issues and pull requests are welcome.

```bash
git clone https://github.com/bensylvenus/django-ninja-boost
cd django-ninja-boost
pip install -e ".[dev]"
pytest --cov=ninja_boost tests/
```

Before opening a PR: all tests pass, new behaviour is covered by a test, docstrings updated for any changed public function signature.

**Reporting bugs** — please include Python version, Django version, django-ninja version, django-ninja-boost version, and a minimal reproduction case.

---

## Publishing to PyPI

```bash
pip install build twine

# Build wheel + source distribution
python -m build

# Validate the distribution
twine check dist/*

# Upload to TestPyPI first
twine upload --repository testpypi dist/*
pip install --index-url https://test.pypi.org/simple/ django-ninja-boost

# Upload to production PyPI
twine upload dist/*
```

---

## Changelog

### 0.1.0 — Initial Release

**New features:**
- `AutoAPI` — drop-in `NinjaAPI` subclass; auto-wires default auth and response envelope
- `AutoRouter` — per-operation auto-wiring of auth, DI, and pagination; opt-outs via `auth=None`, `inject=False`, `paginate=False`
- `inject_context` — injects `ctx = {"user", "ip", "trace_id"}` into every view; X-Forwarded-For aware
- `auto_paginate` — transparent `?page=&size=` pagination; uses `.count()` on QuerySets (no full table loads); ceiling division for page count
- `wrap_response` — standard `{"ok": True, "data": ...}` envelope
- `TracingMiddleware` — UUID trace IDs on every request + `X-Trace-Id` response header
- `register_exception_handlers` — consistent `{"ok": false, "error": ..., "code": ...}` for `HttpError` and generic exceptions
- `BearerTokenAuth` — demo auth backend for local development
- `NinjaBoostConfig` — Django `AppConfig` with startup validation of `NINJA_BOOST` settings
- `BoostSettings` — lazy settings proxy; import cache; `reload()` for tests
- `ninja-boost` CLI — `startproject`, `startapp`, `config` commands

**Bug fixes over the original template:**
- `UserCreate(schema)` → `UserCreate(Schema)` — `schema` was an undefined name
- `urls.py` imported `apps.users.routers` (non-existent path) — corrected
- `AutoAPI.__init__` stored AUTH class not instance — NinjaAPI `auth=` requires an instance
- `auto_paginate` called `len(queryset)` causing full table loads — now uses `.count()` + slice
- CLI entry point referenced non-existent file — `cli.py` created from scratch
- `Apps` missing from `INSTALLED_APPS` — corrected
- `docker-compose.yml` contained stray markdown text making it invalid YAML — cleaned
- Package name inconsistency across files — unified to `django-ninja-boost` / `ninja_boost`
- `AutoAPI.create_response` could double-wrap error responses — fixed with `"ok" in data` guard
- No `AppConfig` for Django app discovery — added `ninja_boost/apps.py`

---

## License

MIT — see [LICENSE](LICENSE).

Copyright (c) 2025 Benjamin Sylvester

---

*If `django-ninja-boost` saves you time, a ⭐ on [GitHub](https://github.com/bensylvenus/django-ninja-boost) goes a long way.*
