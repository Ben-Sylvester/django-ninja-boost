from functools import wraps


def inject_context(func):
    @wraps(func)
    def wrapper(request, *args, **kwargs):
        ctx = {
            "user": request.auth,
            "ip": request.META.get("REMOTE_ADDR"),
            "trace_id": getattr(request, "trace_id", None)
        }
        return func(request, ctx, *args, **kwargs)

    return wrapper
