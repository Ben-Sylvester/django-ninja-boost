import pytest


def pytest_configure(config):
    from django.conf import settings
    if not settings.configured:
        settings.configure(
            DEBUG=True,
            DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
            INSTALLED_APPS=[
                "django.contrib.contenttypes",
                "django.contrib.auth",
                "ninja_boost",
            ],
            MIDDLEWARE=[],
            ROOT_URLCONF="tests.urls",
            NINJA_BOOST={
                "AUTH":             "ninja_boost.integrations.BearerTokenAuth",
                "RESPONSE_WRAPPER": "ninja_boost.responses.wrap_response",
                "PAGINATION":       "ninja_boost.pagination.auto_paginate",
                "DI":               "ninja_boost.dependencies.inject_context",
            },
            USE_TZ=True,
        )
