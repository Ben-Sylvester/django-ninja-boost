from django.contrib import admin
from django.urls import path
from core.api import AutoAPI
from apps.users.routers import router as users_router
from core.exceptions import register_exception_handlers

api = AutoAPI()
api.add_router("/users", users_router)

register_exception_handlers(api)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
]
