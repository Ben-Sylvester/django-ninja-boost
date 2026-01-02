from ninja.errors import HttpError


def register_exception_handlers(api):
    @api.exception_handler(HttpError)
    def http_error(request, exc):
        return api.create_response(
            request,
            {"ok": False, "error": str(exc.message)},
            status=exc.status_code,
        )
