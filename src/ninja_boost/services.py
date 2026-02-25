"""
ninja_boost.services
~~~~~~~~~~~~~~~~~~~~
Auto-service binding and service registry.

The service registry is a central IoC container that maps interface names or
type aliases to concrete service implementations. Services registered here
are automatically injected into views via the context dict (``ctx``).

Defining and registering a service::

    from ninja_boost.services import service_registry, BoostService

    class UserService(BoostService):
        name = "users"

        def list_users(self):
            return User.objects.all()

        def get_user(self, user_id: int):
            return get_object_or_404(User, id=user_id)

    service_registry.register(UserService())

    # Or via settings (auto-loaded on startup):
    NINJA_BOOST = {
        "SERVICES": [
            "apps.users.services.UserService",
            "apps.orders.services.OrderService",
        ],
    }

Using services in views (via ctx["services"])::

    @router.get("/", response=list[UserOut])
    def list_users(request, ctx):
        svc = ctx["services"]["users"]
        return svc.list_users()

Or with the ``@inject_service`` decorator::

    from ninja_boost.services import inject_service

    @router.get("/")
    @inject_service("users", "orders")      # injects ctx["svc_users"], ctx["svc_orders"]
    def dashboard(request, ctx):
        users  = ctx["svc_users"].list_users()
        orders = ctx["svc_orders"].recent()
        ...

Scoped services (per-request instantiation)::

    class RequestScopedService(BoostService):
        name = "scoped"
        scoped = True      # new instance created per request

        def __init__(self):
            self._cache = {}   # request-local cache
"""

import logging
from collections.abc import Callable
from functools import wraps
from typing import Any

from ninja_boost.events import ON_SERVICE_REGISTERED, event_bus

logger = logging.getLogger("ninja_boost.services")


# ── Base service ──────────────────────────────────────────────────────────

class BoostService:
    """
    Base class for all registered services.

    Override ``name`` to set the registry key. If ``scoped = True``, a fresh
    instance is created per request; otherwise the singleton is shared.
    """
    name:   str  = ""
    scoped: bool = False

    def _default_name(self) -> str:
        n = type(self).__name__
        return n.replace("Service", "").lower() or n.lower()

    def get_name(self) -> str:
        return self.name or self._default_name()

    def on_request(self, request: Any, ctx: dict) -> None:
        """
        Called at the start of each request (only for scoped services).
        Override to initialise per-request state.
        """

    def __repr__(self) -> str:
        scope = "scoped" if self.scoped else "singleton"
        return f"<Service {self.get_name()!r} [{scope}]>"


# ── Registry ──────────────────────────────────────────────────────────────

class ServiceRegistry:
    """
    Central service registry / IoC container.
    """

    def __init__(self):
        self._services: dict[str, BoostService | type[BoostService]] = {}

    # ── Registration ──────────────────────────────────────────────────────

    def register(self, service: BoostService | type[BoostService]) -> "ServiceRegistry":
        """
        Register a service instance or class.

        If ``service`` is a class (not an instance), it will be instantiated
        per request (scoped=True semantics regardless of the attribute).
        If it's an instance with ``scoped=False``, it is used as a singleton.
        """
        if isinstance(service, type):
            # Register the class itself — instantiate per request
            key  = service().get_name()
            self._services[key] = service
            logger.info("Service class '%s' registered (scoped)", key)
        else:
            key = service.get_name()
            self._services[key] = service
            logger.info("Service '%s' registered (%s)", key,
                        "scoped" if service.scoped else "singleton")

        event_bus.emit(ON_SERVICE_REGISTERED, service=service, key=key)
        return self

    def unregister(self, name: str) -> None:
        """Remove a service by name."""
        self._services.pop(name, None)

    def get(self, name: str, request: Any = None, ctx: dict | None = None) -> Any:
        """
        Retrieve a service by name, instantiating if scoped.

        Raises KeyError if the service is not registered.
        """
        svc = self._services.get(name)
        if svc is None:
            raise KeyError(
                f"Service '{name}' is not registered. "
                f"Available: {list(self._services.keys())}"
            )

        if isinstance(svc, type):
            # Class registered — create a fresh instance
            instance = svc()
            if request is not None and ctx is not None:
                instance.on_request(request, ctx)
            return instance

        if svc.scoped:
            # Scoped singleton — create a new instance each call
            instance = type(svc)()
            if request is not None and ctx is not None:
                instance.on_request(request, ctx)
            return instance

        return svc  # shared singleton

    def build_context(self, request: Any, ctx: dict) -> dict[str, Any]:
        """
        Build the services sub-dict injected into ctx["services"].

        Scoped services are freshly instantiated. Singletons are shared.
        """
        result = {}
        for name, _svc in self._services.items():
            try:
                result[name] = self.get(name, request=request, ctx=ctx)
            except Exception:
                logger.exception("Failed to build service '%s'", name)
        return result

    @property
    def all(self) -> dict[str, Any]:
        return dict(self._services)

    def load_from_settings(self) -> None:
        """Import and register services from NINJA_BOOST["SERVICES"]."""
        from django.conf import settings
        from django.utils.module_loading import import_string

        cfg = getattr(settings, "NINJA_BOOST", {})
        for dotted_path in cfg.get("SERVICES", []):
            try:
                target = import_string(dotted_path)
                instance = target() if isinstance(target, type) else target
                self.register(instance)
            except Exception:
                logger.exception("Failed to load service '%s'", dotted_path)

    def __len__(self) -> int:
        return len(self._services)

    def __repr__(self) -> str:
        keys = ", ".join(self._services.keys())
        return f"<ServiceRegistry [{keys}]>"


# ── Global singleton ──────────────────────────────────────────────────────
service_registry = ServiceRegistry()


# ── Context enricher ─────────────────────────────────────────────────────

def enrich_ctx_with_services(request: Any, ctx: dict) -> None:
    """
    Add ``ctx["services"]`` populated from the global registry.
    Called by the enhanced inject_context decorator when services are registered.
    """
    if service_registry:
        ctx["services"] = service_registry.build_context(request, ctx)


# ── Decorator ─────────────────────────────────────────────────────────────

def inject_service(*service_names: str):
    """
    Decorator: inject specific services into ctx under ``ctx["svc_{name}"]``.

    Example::

        @router.get("/dashboard")
        @inject_service("users", "orders")
        def dashboard(request, ctx):
            users  = ctx["svc_users"].list_users()
            orders = ctx["svc_orders"].recent()
    """
    def decorator(func: Callable) -> Callable:
        import asyncio as _asyncio

        def _inject(ctx, request):
            for name in service_names:
                try:
                    ctx[f"svc_{name}"] = service_registry.get(name, request, ctx)
                except KeyError as e:
                    logger.error("inject_service: %s", e)

        if _asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(request, ctx: dict, *args, **kwargs) -> Any:
                _inject(ctx, request)
                return await func(request, ctx, *args, **kwargs)
            return async_wrapper

        @wraps(func)
        def wrapper(request, ctx: dict, *args, **kwargs) -> Any:
            _inject(ctx, request)
            return func(request, ctx, *args, **kwargs)
        return wrapper
    return decorator
