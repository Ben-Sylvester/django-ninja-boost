"""
Minimal URL configuration for the test suite.

conftest.py sets ROOT_URLCONF = "tests.urls". Any test that exercises
Django's URL resolver or test client needs this module to exist.
"""
from django.urls import path

urlpatterns: list = []
