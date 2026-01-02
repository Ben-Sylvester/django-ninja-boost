from ninja import Router
from django.utils.module_loading import import_string
from django.conf import settings


class AutoRouter(Router):
    def add_api_operation(self, path, methods, view_func, **kwargs):
        integ = settings.NINJA_INTEGRATIONS

        # auto auth
        if "auth" not in kwargs:
            kwargs["auth"] = import_string(integ["AUTH"])()

        # auto DI injection
        view_func = import_string(integ["DI"])(view_func)

        # auto pagination
        view_func = import_string(integ["PAGINATION"])(view_func)

        return super().add_api_operation(path, methods, view_func, **kwargs)
