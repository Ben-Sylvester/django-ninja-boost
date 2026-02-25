"""
ninja_boost.permissions
~~~~~~~~~~~~~~~~~~~~~~~~
Declarative, composable permission system.

Permissions are callables that receive ``(request, ctx)`` and return
``True`` (allowed) or ``False`` (denied). They can also raise ``HttpError``
directly for custom error messages.

Built-in permissions
--------------------
    IsAuthenticated      — ctx["user"] is not None
    IsStaff              — ctx["user"]["is_staff"] is True
    IsSuperuser          — ctx["user"]["is_superuser"] is True
    AllowAny             — always True (useful as explicit no-auth marker)
    DenyAll              — always False (useful to lock a route completely)
    HasPermission(codename) — Django model permission check
    IsOwner(get_obj_user)   — object-level: caller owns the resource

Composing permissions
---------------------
Permissions can be combined with ``&``, ``|``, ``~``::

    from ninja_boost.permissions import IsAuthenticated, IsStaff, HasPermission

    IsAuthenticatedOrStaff = IsAuthenticated | IsStaff
    ReadOnly = IsAuthenticated & HasPermission("app.view_model")

Usage — per-route decorator::

    from ninja_boost.permissions import require, IsAuthenticated, IsStaff

    @router.get("/admin/report")
    @require(IsStaff)
    def admin_report(request, ctx): ...

    @router.delete("/{id}")
    @require(IsAuthenticated & IsOwner(lambda req, ctx, id: Order.objects.get(id=id).user_id))
    def delete_order(request, ctx, id: int): ...

Global default via settings::

    NINJA_BOOST = {
        "PERMISSIONS": {
            "DEFAULT": "ninja_boost.permissions.IsAuthenticated",
        },
    }
"""

import logging
from functools import wraps
from typing import Any, Callable

from ninja.errors import HttpError
from ninja_boost.events import event_bus, ON_PERMISSION_DENIED

logger = logging.getLogger("ninja_boost.permissions")


# ── Base class ─────────────────────────────────────────────────────────────

class BasePermission:
    """
    Base class for all permission objects.

    Subclass this and implement ``has_permission(request, ctx) -> bool``.
    """

    def has_permission(self, request: Any, ctx: dict) -> bool:
        raise NotImplementedError

    def __call__(self, request: Any, ctx: dict) -> bool:
        return self.has_permission(request, ctx)

    def __and__(self, other: "BasePermission") -> "_AndPermission":
        return _AndPermission(self, other)

    def __or__(self, other: "BasePermission") -> "_OrPermission":
        return _OrPermission(self, other)

    def __invert__(self) -> "_NotPermission":
        return _NotPermission(self)

    def __repr__(self) -> str:
        return self.__class__.__name__


# ── Combinators ───────────────────────────────────────────────────────────

class _AndPermission(BasePermission):
    def __init__(self, left: BasePermission, right: BasePermission):
        self._left, self._right = left, right

    def has_permission(self, request, ctx) -> bool:
        return self._left(request, ctx) and self._right(request, ctx)

    def __repr__(self):
        return f"({self._left!r} & {self._right!r})"


class _OrPermission(BasePermission):
    def __init__(self, left: BasePermission, right: BasePermission):
        self._left, self._right = left, right

    def has_permission(self, request, ctx) -> bool:
        return self._left(request, ctx) or self._right(request, ctx)

    def __repr__(self):
        return f"({self._left!r} | {self._right!r})"


class _NotPermission(BasePermission):
    def __init__(self, inner: BasePermission):
        self._inner = inner

    def has_permission(self, request, ctx) -> bool:
        return not self._inner(request, ctx)

    def __repr__(self):
        return f"~{self._inner!r}"


# ── Built-in permissions ───────────────────────────────────────────────────

class _IsAuthenticated(BasePermission):
    """Allow any authenticated user (ctx["user"] is not None)."""
    def has_permission(self, request, ctx) -> bool:
        return ctx.get("user") is not None

class _IsStaff(BasePermission):
    """Allow users with is_staff=True in their auth payload."""
    def has_permission(self, request, ctx) -> bool:
        user = ctx.get("user")
        if user is None:
            return False
        if isinstance(user, dict):
            return bool(user.get("is_staff"))
        return bool(getattr(user, "is_staff", False))

class _IsSuperuser(BasePermission):
    """Allow users with is_superuser=True in their auth payload."""
    def has_permission(self, request, ctx) -> bool:
        user = ctx.get("user")
        if user is None:
            return False
        if isinstance(user, dict):
            return bool(user.get("is_superuser"))
        return bool(getattr(user, "is_superuser", False))

class _AllowAny(BasePermission):
    """Always allow — explicit opt-in to public access."""
    def has_permission(self, request, ctx) -> bool:
        return True

class _DenyAll(BasePermission):
    """Always deny — locks a route completely (useful during maintenance)."""
    def has_permission(self, request, ctx) -> bool:
        return False


# Public singletons (use these directly, no need to instantiate)
IsAuthenticated = _IsAuthenticated()
IsStaff         = _IsStaff()
IsSuperuser     = _IsSuperuser()
AllowAny        = _AllowAny()
DenyAll         = _DenyAll()


class HasPermission(BasePermission):
    """
    Check a Django model-level permission codename.

    Example::

        @require(HasPermission("shop.add_product"))
        def create_product(request, ctx, payload): ...
    """
    def __init__(self, codename: str):
        self._codename = codename

    def has_permission(self, request, ctx) -> bool:
        user = ctx.get("user")
        if user is None:
            return False
        # Support both Django User objects and dict payloads
        if hasattr(user, "has_perm"):
            return user.has_perm(self._codename)
        if isinstance(user, dict):
            # Dict-based payloads can include a "permissions" list
            perms = user.get("permissions", [])
            return self._codename in perms or self._codename.split(".")[-1] in perms
        return False

    def __repr__(self):
        return f"HasPermission({self._codename!r})"


class IsOwner(BasePermission):
    """
    Object-level permission: caller's user ID must match the object owner.

    Parameters
    ----------
    get_owner_id:
        Callable ``(request, ctx, **path_kwargs) -> int | str``
        that returns the owner's user ID.

    Example::

        IsOrderOwner = IsOwner(
            lambda req, ctx, id, **kw: Order.objects.get(id=id).user_id
        )

        @router.delete("/{id}")
        @require(IsOrderOwner)
        def delete_order(request, ctx, id: int): ...
    """
    def __init__(self, get_owner_id: Callable):
        self._get_owner_id = get_owner_id

    def has_permission(self, request, ctx, **path_kwargs) -> bool:
        user = ctx.get("user")
        if user is None:
            return False
        uid = (user.get("id") or user.get("user_id")) if isinstance(user, dict) else getattr(user, "id", None)
        try:
            owner_id = self._get_owner_id(request, ctx, **path_kwargs)
            return str(uid) == str(owner_id)
        except Exception:
            logger.exception("IsOwner.get_owner_id raised")
            return False

    def __repr__(self):
        return "IsOwner(...)"


class RatePermission(BasePermission):
    """
    Permission that checks if a specific condition is rate-limited.
    Useful for feature gating (e.g. free tier limits).
    """
    def __init__(self, check_fn: Callable, denied_message: str = "Quota exceeded."):
        self._check_fn = check_fn
        self._denied_message = denied_message

    def has_permission(self, request, ctx) -> bool:
        return bool(self._check_fn(request, ctx))


# ── Decorator ─────────────────────────────────────────────────────────────

def require(
    *permissions: BasePermission | Callable,
    message: str = "Permission denied.",
    status: int = 403,
):
    """
    Decorator: enforce one or more permissions on a view.

    All permissions must pass (AND logic). Use ``|`` to compose OR logic::

        @require(IsAuthenticated | AllowAny)
        @require(IsStaff & HasPermission("reports.view"))

    Raises ``HttpError(status, message)`` on failure.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(request, ctx: dict, *args, **kwargs) -> Any:
            for perm in permissions:
                # Pass path kwargs to permissions that need them (e.g. IsOwner)
                try:
                    if isinstance(perm, IsOwner):
                        allowed = perm.has_permission(request, ctx, **kwargs)
                    else:
                        allowed = perm(request, ctx)
                except HttpError:
                    raise
                except Exception:
                    logger.exception("Permission %r raised unexpectedly", perm)
                    allowed = False

                if not allowed:
                    perm_name = repr(perm)
                    event_bus.emit(
                        ON_PERMISSION_DENIED,
                        request=request,
                        ctx=ctx,
                        permission=perm_name,
                    )
                    logger.warning(
                        "Permission denied: user=%s path=%s permission=%s",
                        ctx.get("user"), request.path, perm_name,
                    )
                    raise HttpError(status, message)

            return func(request, ctx, *args, **kwargs)

        # Attach metadata for introspection / OpenAPI
        wrapper._permissions = list(permissions)
        return wrapper

    return decorator


# ── Async variant ─────────────────────────────────────────────────────────

def require_async(
    *permissions: BasePermission | Callable,
    message: str = "Permission denied.",
    status: int = 403,
):
    """Async-compatible variant of ``require``."""
    import asyncio

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(request, ctx: dict, *args, **kwargs) -> Any:
            for perm in permissions:
                try:
                    if asyncio.iscoroutinefunction(perm.__call__):
                        allowed = await perm(request, ctx)
                    elif isinstance(perm, IsOwner):
                        allowed = perm.has_permission(request, ctx, **kwargs)
                    else:
                        allowed = perm(request, ctx)
                except HttpError:
                    raise
                except Exception:
                    logger.exception("Async permission %r raised", perm)
                    allowed = False

                if not allowed:
                    event_bus.emit(ON_PERMISSION_DENIED, request=request, ctx=ctx,
                                   permission=repr(perm))
                    raise HttpError(status, message)

            return await func(request, ctx, *args, **kwargs)

        wrapper._permissions = list(permissions)
        return wrapper

    return decorator
