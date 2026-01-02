from functools import wraps


def auto_paginate(func):
    @wraps(func)
    def wrapper(request, *args, **kwargs):
        result = func(request, *args, **kwargs)

        if hasattr(result, "__iter__") and not isinstance(result, dict):
            page = int(request.GET.get("page", 1))
            size = int(request.GET.get("size", 20))

            start = (page - 1) * size
            end = start + size

            return {
                "items": result[start:end],
                "page": page,
                "size": size,
                "total": len(result)
            }

        return result

    return wrapper
