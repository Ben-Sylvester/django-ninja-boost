import uuid


class TracingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.trace_id = uuid.uuid4().hex
        return self.get_response(request)
