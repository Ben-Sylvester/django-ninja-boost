"""
ninja_boost.policies
~~~~~~~~~~~~~~~~~~~~
Resource-level policy registry.

Policies encode "can user X perform action Y on resource Z?" as reusable,
named rule sets. Unlike permissions (which are route-decorators), policies
are registered in a central registry and evaluated imperatively inside views.

This mirrors the Policy pattern from Laravel/Pundit — all access rules for a
resource live in one class rather than scattered across route decorators.

Defining a policy::

    from ninja_boost.policies import BasePolicy, policy_registry
    from .models import Order

    class OrderPolicy(BasePolicy):
        resource = Order          # optional — for automatic bind in service layer
        resource_name = "order"   # key used in registry lookup

        def view(self, request, ctx, obj=None) -> bool:
            \"\"\"Anyone authenticated can view orders they own.\"\"\"\
            return obj is None or str(obj.user_id) == str(ctx["user"]["id"])

        def create(self, request, ctx, obj=None) -> bool:
            return ctx["user"] is not None

        def update(self, request, ctx, obj=None) -> bool:
            return obj is not None and str(obj.user_id) == str(ctx["user"]["id"])

        def delete(self, request, ctx, obj=None) -> bool:
            return ctx["user"].get("is_staff", False)

    policy_registry.register(OrderPolicy())

Checking a policy inside a view::

    from ninja_boost.policies import policy_registry

    @router.put("/{id}")
    def update_order(request, ctx, id: int, payload: OrderUpdate):
        order = get_object_or_404(Order, id=id)
        policy_registry.authorize(request, ctx, "order", "update", obj=order)
        return OrderService.update(order, payload)

Using the ``@policy`` decorator::

    from ninja_boost.policies import policy

    @router.delete("/{id}")
    @policy("order", "delete", get_obj=lambda id, **kw: Order.objects.get(id=id))
    def delete_order(request, ctx, id: int): ...

Auto-loading from settings::

    NINJA_BOOST = {
        "POLICIES": [
            "apps.orders.policies.OrderPolicy",
            "apps.products.policies.ProductPolicy",
        ],
    }
"""

import logging
from collections.abc import Callable
from functools import wraps
from typing import Any

from ninja.errors import HttpError

from ninja_boost.events import ON_POLICY_DENIED, event_bus

logger = logging.getLogger("ninja_boost.policies")


# ── Base policy ───────────────────────────────────────────────────────────

class BasePolicy:
    """
    Base class for all resource policies.

    ``resource_name`` is the key used when looking up this policy in the
    registry. It defaults to the class name without the word "Policy".
    """
    resource_name: str = ""
    resource: type | None = None

    def _default_name(self) -> str:
        name = type(self).__name__
        return name.replace("Policy", "").lower() or name.lower()

    def get_resource_name(self) -> str:
        return self.resource_name or self._default_name()

    def before(self, request: Any, ctx: dict, action: str, obj: Any = None) -> bool | None:
        """
        Optional pre-check. Return True to allow unconditionally,
        False to deny unconditionally, or None to continue to action check.

        Useful for superuser bypass::

            def before(self, request, ctx, action, obj=None):
                if ctx["user"].get("is_superuser"):
                    return True   # superusers skip all policy checks
                return None
        """
        return None

    def __repr__(self) -> str:
        return f"<Policy {self.get_resource_name()!r}>"


# ── Registry ──────────────────────────────────────────────────────────────

class PolicyRegistry:
    """
    Global policy registry.

    Maps resource names to BasePolicy instances and provides a single
    ``authorize`` entry-point for checking access.
    """

    def __init__(self):
        self._policies: dict[str, BasePolicy] = {}

    # ── Registration ──────────────────────────────────────────────────────

    def register(self, policy: BasePolicy) -> "PolicyRegistry":
        """Register a policy. Returns self for chaining."""
        key = policy.get_resource_name()
        if key in self._policies:
            logger.warning(
                "Policy for resource '%s' is being replaced. "
                "Call unregister() first if this is intentional.", key
            )
        self._policies[key] = policy
        logger.info("Policy registered for resource '%s'", key)
        return self

    def unregister(self, resource_name: str) -> None:
        """Remove a policy by resource name."""
        self._policies.pop(resource_name, None)

    def get(self, resource_name: str) -> BasePolicy | None:
        """Return the policy for *resource_name*, or None."""
        return self._policies.get(resource_name)

    @property
    def all(self) -> dict[str, BasePolicy]:
        return dict(self._policies)

    # ── Evaluation ────────────────────────────────────────────────────────

    def authorize(
        self,
        request: Any,
        ctx: dict,
        resource_name: str,
        action: str,
        obj: Any = None,
        raise_on_deny: bool = True,
        status: int = 403,
        message: str | None = None,
    ) -> bool:
        """
        Evaluate a policy action. Raises ``HttpError(403)`` on denial by default.

        Parameters
        ----------
        request, ctx:
            Standard Django request and boost context dict.
        resource_name:
            Key used when the policy was registered.
        action:
            Method name on the policy class (e.g. "view", "create", "update").
        obj:
            Optional resource instance for object-level checks.
        raise_on_deny:
            If True (default), raise HttpError on failure instead of returning False.
        """
        policy = self._policies.get(resource_name)
        if policy is None:
            logger.warning(
                "No policy registered for resource '%s'. Denying by default.", resource_name
            )
            if raise_on_deny:
                raise HttpError(403, message or f"No policy for '{resource_name}'.")
            return False

        # Run before() pre-check
        pre = policy.before(request, ctx, action, obj=obj)
        if pre is True:
            return True
        if pre is False:
            self._deny(request, ctx, resource_name, action, raise_on_deny, status, message)
            return False

        # Run the action method
        action_fn = getattr(policy, action, None)
        if action_fn is None:
            logger.warning("Policy '%s' has no action '%s'. Denying.", resource_name, action)
            self._deny(request, ctx, resource_name, action, raise_on_deny, status, message)
            return False

        try:
            allowed = bool(action_fn(request, ctx, obj=obj))
        except HttpError:
            raise
        except Exception:
            logger.exception("Policy '%s.%s' raised unexpectedly", resource_name, action)
            allowed = False

        if not allowed:
            self._deny(request, ctx, resource_name, action, raise_on_deny, status, message)
            return False

        return True

    def can(
        self,
        request: Any,
        ctx: dict,
        resource_name: str,
        action: str,
        obj: Any = None,
    ) -> bool:
        """Non-raising variant of ``authorize``. Returns True/False."""
        return self.authorize(
            request, ctx, resource_name, action, obj=obj, raise_on_deny=False
        )

    def _deny(self, request, ctx, resource_name, action,
              raise_on_deny, status, message) -> None:
        denial_message = message or f"Not authorized to perform '{action}' on '{resource_name}'."
        event_bus.emit(
            ON_POLICY_DENIED,
            request=request,
            ctx=ctx,
            resource=resource_name,
            action=action,
        )
        logger.warning(
            "Policy denied: user=%s resource=%s action=%s",
            ctx.get("user"), resource_name, action,
        )
        if raise_on_deny:
            raise HttpError(status, denial_message)

    def load_from_settings(self) -> None:
        """Import and register policies from NINJA_BOOST["POLICIES"]."""
        from django.conf import settings
        from django.utils.module_loading import import_string

        cfg = getattr(settings, "NINJA_BOOST", {})
        for dotted_path in cfg.get("POLICIES", []):
            try:
                cls = import_string(dotted_path)
                instance = cls() if isinstance(cls, type) else cls
                self.register(instance)
            except Exception:
                logger.exception("Failed to load policy '%s'", dotted_path)

    def __len__(self) -> int:
        return len(self._policies)

    def __repr__(self) -> str:
        keys = ", ".join(self._policies.keys())
        return f"<PolicyRegistry [{keys}]>"


# ── Global singleton ──────────────────────────────────────────────────────
policy_registry = PolicyRegistry()


# ── Route decorator ───────────────────────────────────────────────────────

def policy(
    resource_name: str,
    action: str,
    get_obj: Callable | None = None,
    status: int = 403,
    message: str | None = None,
):
    """
    Decorator: enforce a policy action on a route.

    Parameters
    ----------
    resource_name:
        Key of the registered policy.
    action:
        Policy action method to call (e.g. "update", "delete").
    get_obj:
        Optional callable ``(**path_kwargs) -> object`` to fetch the resource
        instance for object-level checks.

    Example::

        @router.delete("/{id}")
        @policy("order", "delete", get_obj=lambda id, **kw: Order.objects.get(id=id))
        def delete_order(request, ctx, id: int): ...
    """
    def decorator(func: Callable) -> Callable:
        import asyncio as _asyncio

        def _authorize(request, ctx, kwargs):
            obj = None
            if get_obj is not None:
                try:
                    obj = get_obj(**kwargs)
                except Exception as exc:
                    raise HttpError(404, "Resource not found.") from exc
            policy_registry.authorize(
                request, ctx, resource_name, action,
                obj=obj, status=status, message=message,
            )

        if _asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(request, ctx: dict, *args, **kwargs) -> Any:
                _authorize(request, ctx, kwargs)
                return await func(request, ctx, *args, **kwargs)
            async_wrapper._policy_resource = resource_name
            async_wrapper._policy_action   = action
            return async_wrapper

        @wraps(func)
        def wrapper(request, ctx: dict, *args, **kwargs) -> Any:
            _authorize(request, ctx, kwargs)
            return func(request, ctx, *args, **kwargs)

        wrapper._policy_resource = resource_name
        wrapper._policy_action   = action
        return wrapper

    return decorator
