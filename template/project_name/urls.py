from apps.users.routers import router as users_router
from django.contrib import admin
from django.urls import path

from ninja_boost import AutoAPI
from ninja_boost.exceptions import register_exception_handlers

api = AutoAPI(title="My API", version="1.0")
register_exception_handlers(api)
api.add_router("/users", users_router)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
]
