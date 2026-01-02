from ninja import NinjaAPI
from django.conf import settings
from django.utils.module_loading import import_string


class AutoAPI(NinjaAPI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        integ = settings.NINJA_INTEGRATIONS

        self.default_auth = import_string(integ["AUTH"])
        self.response_wrapper = import_string(integ["RESPONSE_WRAPPER"])
        self.auto_paginate = import_string(integ["PAGINATION"])
        self.di = import_string(integ["DI"])

    def create_response(self, request, data, *args, **kwargs):
        data = self.response_wrapper(data)
        return super().create_response(request, data, *args, **kwargs)
