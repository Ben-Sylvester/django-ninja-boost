
# Django Ninja Automation

**Django Ninja Automation** is the backbone for developers using **Django Ninja** who want to streamline backend development.

It eliminates repetitive work—API setup, routing, dependencies, exception handling, pagination, responses, and middleware—so you can focus on writing business logic instead of boilerplate.

You drop it into an existing Django backend and it becomes the **automation hub** for your APIs.

> Set it up once. Write APIs. Everything else just works.

---

## What This Library Is

* A **backend automation core**
* An **enhancement layer** for Django Ninja
* A **plug-and-play library** for Django projects

## What This Library Is NOT

*  It does **not** generate a Django project for you
*  It is **not** a code generator
*  It does **not** replace Django or Django Ninja

Think of it as a **powerful extension**, not a substitute.

### Key Distinction

* **`core/`** → What this package provides
* **`Apps/`** → How developers use it


## Core Features

### Central API Automation (`core/api.py`)

Provides a **single, standardized Ninja API instance** for the entire project.

**Automates:**

* API creation
* API configuration
* Documentation consistency

You no longer create `NinjaAPI()` per app.

###  Router Automation (`core/router.py`)

Centralizes router registration across all apps.

**Automates:**

* Router aggregation
* Router versioning
* Clean API composition

 No manual router wiring in multiple places.

### Dependency Automation (`core/dependencies.py`)

Reusable dependencies for:

* Authentication
* Authorization
* Request context
* Shared logic

No duplicated auth or context logic per endpoint.

---

### 4. Unified Exception Handling (`core/exceptions.py`)

Provides:

* Custom API exception classes
* Consistent error formatting
* Centralized error responses

 No `try/except` blocks scattered everywhere.

---

### 5. Pagination Engine (`core/pagination.py`)

Standard pagination logic for all endpoints.

**Automates:**

* Page handling
* Limit/offset logic
* Paginated response format

 No re-implementing pagination per endpoint.

---

### 6. Response Standardization (`core/responses.py`)

Defines a **single response contract** for success and failure.

 No manual JSON shaping.

---

### 7. Middleware Automation (`core/middleware.py`)

Handles:

* Request preprocessing
* Response postprocessing
* Logging / tracing hooks

 No cross-cutting logic scattered across views.

---

## Installation

```bash
pip install django-ninja-automation
```

---

##  Dependency Handling (Important)

* All **runtime dependencies** are installed automatically:

  * `django`
  * `django-ninja`
  * `pydantic`

* The library ships with:

  * A Django **backend project**
  * An example app called **`Apps`**

You may:

* Add more apps freely
* Modify structure to suit your needs

> `requirements.txt` is **for development only** when cloning from
> `github.com/ben-sylvester/Django-ninja-automation`

---

## Step-by-Step Usage Guide

### 1. Register the Core API

**File:** `core/api.py` (already provided)

* Exposes a shared Ninja API instance
* **Do NOT create `NinjaAPI()` anywhere else**

---

### 2. Configure URLs

**File:** `backend/urls.py`

```python
from django.urls import path
from core.api import api

urlpatterns = [
    path("api/", api.urls),
]
```

This automatically connects **all registered routers**.

---

### 3. Register Routers

**File:** `core/router.py`

Routers from all apps are registered **once** here.

**App usage example:**

```python
# Apps/routers.py
from ninja import Router

router = Router()

@router.get("/health")
def health(request):
    return {"status": "ok"}
```

 No manual router inclusion in `urls.py`.

---

### 4. Use Dependencies

**File:** `Apps/routers.py`

```python
from core.dependencies import auth_dependency

@router.get("/secure", dependencies=[auth_dependency])
def secure_endpoint(request):
    return {"secure": True}
```

 Auth logic is centralized and reusable.

---

### 5. Use Standard Responses

**File:** `Apps/routers.py`

```python
from core.responses import success_response

@router.get("/data")
def get_data(request):
    return success_response(data={"value": 123})
```

 Response shape is consistent everywhere.

---

### 7. Use Pagination

**File:** `Apps/services.py`

```python
from core.pagination import paginate

def list_items(queryset, request):
    return paginate(queryset, request)
```

 Pagination logic is centralized.

---

### 7. Handle Errors Automatically

**File:** `Apps/services.py`

```python
from core.exceptions import APIException

if not item:
    raise APIException("Item not found", status_code=404)
```

 No manual error formatting required.

---

## What Developers No Longer Need To Do

Thanks to the automation core, developers no longer need to:

*  Manually create Ninja API instances
*  Repeat pagination logic
*  Write inconsistent JSON responses
*  Scatter exception handling
*  Duplicate authentication logic
*  Manually wire routers everywhere

---

## How Developers Navigate the App

* `core/` → framework & automation
* `Apps/` → business logic

Inside each app:

* `routers.py` → API endpoints
* `schemas.py` → request/response validation
* `services.py` → business logic
* `models.py` → data layer

---

## Intended Use Cases

* Enterprise APIs
* Automation platforms
* Internal service backends
* AI / data orchestration APIs
* Large Django-Ninja projects

---

## Final Clarity

This library **does not replace Django Ninja**.

It **removes repetition** and **enforces standards** on top of it.

That’s exactly what an **automation core** should do.
