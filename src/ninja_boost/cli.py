"""
ninja_boost.cli
~~~~~~~~~~~~~~~
``ninja-boost`` — CLI scaffolding tool.

Commands
--------
    ninja-boost startproject <name>    Scaffold a complete new project
    ninja-boost startapp <name>        Scaffold a new app in apps/<name>/
    ninja-boost config                 Print a starter NINJA_BOOST settings block

Usage::

    pip install django-ninja-boost
    ninja-boost startproject myapi
    cd myapi && pip install -r requirements.txt
    python manage.py migrate && python manage.py runserver
"""

import argparse
import sys
import textwrap
from pathlib import Path


# ── Starter code templates ─────────────────────────────────────────────────

SETTINGS_BLOCK = textwrap.dedent("""\
    # ── Django Ninja Boost ────────────────────────────────────────────────────
    INSTALLED_APPS += ["ninja_boost"]

    MIDDLEWARE += ["ninja_boost.middleware.TracingMiddleware"]

    NINJA_BOOST = {
        # Replace with a real JWT/session auth in production
        "AUTH":             "ninja_boost.integrations.BearerTokenAuth",
        # Envelope: {"ok": True, "data": ...}
        "RESPONSE_WRAPPER": "ninja_boost.responses.wrap_response",
        # Auto-paginate lists and QuerySets via ?page=&size=
        "PAGINATION":       "ninja_boost.pagination.auto_paginate",
        # Inject ctx = {user, ip, trace_id} into every view
        "DI":               "ninja_boost.dependencies.inject_context",
    }
    # ─────────────────────────────────────────────────────────────────────────
""")

ROUTER_TPL = textwrap.dedent("""\
    from ninja_boost import AutoRouter
    from .schemas import {Cap}Out, {Cap}Create
    from .services import {Cap}Service

    router = AutoRouter(tags=["{Cap}"])


    @router.get("/", response=list[{Cap}Out])
    def list_{lower}s(request, ctx):
        \"\"\"List all {lower}s. Auto-paginated via ?page=&size=. \"\"\"
        return {Cap}Service.list_{lower}s()


    @router.get("/{{id}}", response={Cap}Out)
    def get_{lower}(request, ctx, id: int):
        \"\"\"Retrieve a single {lower} by ID.\"\"\"
        return {Cap}Service.get_{lower}(id)


    @router.post("/", response={Cap}Out, paginate=False)
    def create_{lower}(request, ctx, payload: {Cap}Create):
        \"\"\"Create a new {lower}.\"\"\"
        return {Cap}Service.create_{lower}(payload)
""")

SCHEMAS_TPL = textwrap.dedent("""\
    from ninja import Schema
    from typing import Optional


    class {Cap}Out(Schema):
        id: int
        name: str


    class {Cap}Create(Schema):
        name: str


    class {Cap}Update(Schema):
        name: Optional[str] = None
""")

SERVICES_TPL = textwrap.dedent("""\
    from .schemas import {Cap}Create, {Cap}Out
    # from django.shortcuts import get_object_or_404
    # from .models import {Cap}


    class {Cap}Service:

        @staticmethod
        def list_{lower}s():
            # Return a QuerySet for efficient auto-pagination:
            # return {Cap}.objects.all()
            raise NotImplementedError

        @staticmethod
        def get_{lower}(id: int) -> {Cap}Out:
            # return get_object_or_404({Cap}, id=id)
            raise NotImplementedError

        @staticmethod
        def create_{lower}(data: {Cap}Create) -> {Cap}Out:
            raise NotImplementedError
""")

APPCONFIG_TPL = textwrap.dedent("""\
    from django.apps import AppConfig


    class {Cap}Config(AppConfig):
        name = "apps.{lower}"
        verbose_name = "{Cap}"
""")


# ── Helpers ────────────────────────────────────────────────────────────────

def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  created  {path}")


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("", encoding="utf-8")
        print(f"  created  {path}")


# ── Commands ───────────────────────────────────────────────────────────────

def cmd_startproject(name: str) -> None:
    root = Path(name)
    if root.exists():
        print(f"[ninja-boost] Error: '{name}' already exists.", file=sys.stderr)
        sys.exit(1)

    print(f"\n  Scaffolding project: {name}\n")
    pkg = root / name

    _write(root / "manage.py", textwrap.dedent(f"""\
        #!/usr/bin/env python
        import os, sys

        def main():
            os.environ.setdefault("DJANGO_SETTINGS_MODULE", "{name}.settings")
            from django.core.management import execute_from_command_line
            execute_from_command_line(sys.argv)

        if __name__ == "__main__":
            main()
    """))

    _write(pkg / "__init__.py", "")

    _write(pkg / "settings.py", textwrap.dedent(f"""\
        from pathlib import Path

        BASE_DIR = Path(__file__).resolve().parent.parent
        SECRET_KEY = "django-insecure-CHANGE-ME-BEFORE-DEPLOYMENT"
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

        NINJA_BOOST = {{
            "AUTH":             "ninja_boost.integrations.BearerTokenAuth",
            "RESPONSE_WRAPPER": "ninja_boost.responses.wrap_response",
            "PAGINATION":       "ninja_boost.pagination.auto_paginate",
            "DI":               "ninja_boost.dependencies.inject_context",
        }}

        ROOT_URLCONF = "{name}.urls"

        TEMPLATES = [{{
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "DIRS": [],
            "APP_DIRS": True,
            "OPTIONS": {{
                "context_processors": [
                    "django.template.context_processors.debug",
                    "django.template.context_processors.request",
                    "django.contrib.auth.context_processors.auth",
                    "django.contrib.messages.context_processors.messages",
                ],
            }},
        }}]

        WSGI_APPLICATION = "{name}.wsgi.application"

        DATABASES = {{
            "default": {{
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": BASE_DIR / "db.sqlite3",
            }}
        }}

        LANGUAGE_CODE = "en-us"
        TIME_ZONE = "UTC"
        USE_I18N = True
        USE_TZ = True
        STATIC_URL = "static/"
        DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
    """))

    _write(pkg / "urls.py", textwrap.dedent(f"""\
        from django.contrib import admin
        from django.urls import path
        from ninja_boost import AutoAPI
        from ninja_boost.exceptions import register_exception_handlers

        api = AutoAPI(title="{name} API", version="1.0")
        register_exception_handlers(api)

        # Add your app routers here:
        # from apps.users.routers import router as users_router
        # api.add_router("/users", users_router)

        urlpatterns = [
            path("admin/", admin.site.urls),
            path("api/", api.urls),
        ]
    """))

    _write(pkg / "wsgi.py", textwrap.dedent(f"""\
        import os
        from django.core.wsgi import get_wsgi_application
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "{name}.settings")
        application = get_wsgi_application()
    """))

    _write(pkg / "asgi.py", textwrap.dedent(f"""\
        import os
        from django.core.asgi import get_asgi_application
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "{name}.settings")
        application = get_asgi_application()
    """))

    _write(root / "requirements.txt",
           "Django>=4.2\ndjango-ninja>=0.21.0\ndjango-ninja-boost\n")

    _write(root / "pytest.ini",
           f"[pytest]\nDJANGO_SETTINGS_MODULE = {name}.settings\n")

    _touch(root / "apps" / "__init__.py")

    print(f"\n  ✅  Project '{name}' created.\n")
    print(f"  Next:\n    cd {name}\n    pip install -r requirements.txt\n"
          f"    python manage.py migrate\n    python manage.py runserver\n")


def cmd_startapp(name: str) -> None:
    root = Path("apps") / name
    if root.exists():
        print(f"[ninja-boost] Error: 'apps/{name}' already exists.", file=sys.stderr)
        sys.exit(1)

    cap = name.capitalize()
    print(f"\n  Scaffolding app: {name}\n")

    _touch(root / "__init__.py")
    _write(root / "routers.py",  ROUTER_TPL.format(Cap=cap, lower=name))
    _write(root / "schemas.py",  SCHEMAS_TPL.format(Cap=cap))
    _write(root / "services.py", SERVICES_TPL.format(Cap=cap, lower=name))
    _write(root / "models.py",   "from django.db import models\n")
    _write(root / "admin.py",    "from django.contrib import admin\n")
    _write(root / "apps.py",     APPCONFIG_TPL.format(Cap=cap, lower=name))
    _touch(root / "migrations" / "__init__.py")

    print(f"\n  ✅  App '{name}' created in apps/{name}/\n")
    print(f"  Register in settings.py INSTALLED_APPS:\n    \"apps.{name}\",\n")
    print(f"  Register in urls.py:\n"
          f"    from apps.{name}.routers import router as {name}_router\n"
          f"    api.add_router(\"/{name}s\", {name}_router)\n")


def cmd_config() -> None:
    print("\n  Add to your settings.py:\n")
    print(SETTINGS_BLOCK)


# ── Entrypoint ─────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ninja-boost",
        description="Django Ninja Boost — project and app scaffolding",
    )
    subs = parser.add_subparsers(dest="command", required=True)

    p = subs.add_parser("startproject", help="Scaffold a new project")
    p.add_argument("name")

    a = subs.add_parser("startapp", help="Scaffold a new app")
    a.add_argument("name")

    subs.add_parser("config", help="Print starter NINJA_BOOST settings block")

    args = parser.parse_args()

    {"startproject": cmd_startproject,
     "startapp":     cmd_startapp,
     "config":       lambda: cmd_config()}.get(
        args.command,
        lambda *_: parser.print_help()
    )(getattr(args, "name", None))


if __name__ == "__main__":
    main()
