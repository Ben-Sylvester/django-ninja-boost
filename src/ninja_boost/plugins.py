"""
ninja_boost.plugins
~~~~~~~~~~~~~~~~~~~
Plugin architecture — extend ninja_boost without forking it.

A plugin is a class that inherits ``BoostPlugin`` and overrides the hooks
it needs. Plugins are registered once and automatically participate in the
request lifecycle via the event bus.

Creating a plugin::

    from ninja_boost.plugins import BoostPlugin, plugin_registry

    class AuditPlugin(BoostPlugin):
        name = "audit"
        version = "1.0"

        def on_startup(self, api):
            print(f"Audit plugin attached to {api.title}")

        def on_request(self, request, ctx, **kw):
            AuditLog.objects.create(
                user_id=ctx["user"].get("id"),
                path=request.path,
                ip=ctx["ip"],
            )

        def on_error(self, request, exc, ctx, **kw):
            Sentry.capture_exception(exc)

    plugin_registry.register(AuditPlugin())

Registering via settings (auto-loaded on startup)::

    NINJA_BOOST = {
        ...
        "PLUGINS": [
            "myproject.plugins.AuditPlugin",
            "myproject.plugins.SentryPlugin",
        ],
    }

Available hooks
---------------
    on_startup(api)                     called when AutoAPI is created
    on_request(request, ctx)            called before every view
    on_response(request, response, ctx, duration_ms)  called after response created
    on_error(request, exc, ctx)         called on unhandled exceptions
    on_auth_failure(request)            called when auth returns None
    on_rate_limit_exceeded(request, key, rate) called when rate limit hit
    on_permission_denied(request, ctx, permission) called on permission failure
"""

import logging
from typing import Any

from ninja_boost.events import event_bus, BEFORE_REQUEST, AFTER_RESPONSE, ON_ERROR
from ninja_boost.events import ON_AUTH_FAILURE, ON_RATE_LIMIT_EXCEEDED, ON_PERMISSION_DENIED

logger = logging.getLogger("ninja_boost.plugins")


class BoostPlugin:
    """
    Base class for all ninja_boost plugins.

    Override only the hooks you need. All hooks are optional.
    """
    name:    str = "unnamed"
    version: str = "0.0.0"
    enabled: bool = True

    def on_startup(self, api: Any) -> None:
        """Called once when the AutoAPI instance is created."""

    def on_request(self, request: Any, ctx: dict, **kw) -> None:
        """Called before every view function. Raise HttpError to abort."""

    def on_response(self, request: Any, response: Any, ctx: dict,
                    duration_ms: float, **kw) -> None:
        """Called after the response is built but before it is returned."""

    def on_error(self, request: Any, exc: Exception, ctx: dict, **kw) -> None:
        """Called when an unhandled exception occurs in a view."""

    def on_auth_failure(self, request: Any, **kw) -> None:
        """Called when the auth backend returns None (authentication failed)."""

    def on_rate_limit_exceeded(self, request: Any, key: str, rate: str, **kw) -> None:
        """Called when a rate limit is breached."""

    def on_permission_denied(self, request: Any, ctx: dict,
                              permission: str, **kw) -> None:
        """Called when a declarative permission check fails."""

    def __repr__(self) -> str:
        return f"<Plugin {self.name} v{self.version}>"


class PluginRegistry:
    """
    Global plugin registry.

    Plugins are registered here and their hooks are wired into the event bus
    automatically on registration.
    """

    def __init__(self):
        self._plugins: list[BoostPlugin] = []

    # ── Registration ─────────────────────────────────────────────────────

    def register(self, plugin: BoostPlugin) -> "PluginRegistry":
        """Register a plugin instance. Returns self for chaining."""
        if not plugin.enabled:
            logger.info("Plugin '%s' is disabled — skipping", plugin.name)
            return self

        if any(p.name == plugin.name for p in self._plugins):
            raise ValueError(
                f"A plugin named '{plugin.name}' is already registered. "
                "Set a unique `name` on your plugin class."
            )

        self._plugins.append(plugin)
        self._wire_events(plugin)

        event_bus.emit("on_plugin_loaded", plugin=plugin)
        logger.info("Plugin '%s' v%s registered", plugin.name, plugin.version)
        return self

    def unregister(self, name: str) -> None:
        """Remove a plugin by name."""
        self._plugins = [p for p in self._plugins if p.name != name]

    def get(self, name: str) -> BoostPlugin | None:
        """Return a plugin by name, or None."""
        return next((p for p in self._plugins if p.name == name), None)

    @property
    def all(self) -> list[BoostPlugin]:
        return list(self._plugins)

    # ── Event wiring ──────────────────────────────────────────────────────

    def _wire_events(self, plugin: BoostPlugin) -> None:
        """Subscribe plugin hook methods to the global event bus."""
        mapping = {
            BEFORE_REQUEST:         plugin.on_request,
            AFTER_RESPONSE:         plugin.on_response,
            ON_ERROR:               plugin.on_error,
            ON_AUTH_FAILURE:        plugin.on_auth_failure,
            ON_RATE_LIMIT_EXCEEDED: plugin.on_rate_limit_exceeded,
            ON_PERMISSION_DENIED:   plugin.on_permission_denied,
        }
        for event, method in mapping.items():
            # Only subscribe if the plugin has overridden the hook
            if type(plugin).__dict__.get(method.__func__.__name__) is not None:
                event_bus._handlers[event].append(method)

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def fire_startup(self, api: Any) -> None:
        """Called by AutoAPI.__init__ — notifies all plugins of the new API instance."""
        for plugin in self._plugins:
            try:
                plugin.on_startup(api)
            except Exception:
                logger.exception("Plugin '%s' raised in on_startup", plugin.name)

    def load_from_settings(self) -> None:
        """
        Import and register plugins listed in NINJA_BOOST["PLUGINS"].
        Called automatically by NinjaBoostConfig.ready().
        """
        from django.conf import settings
        from django.utils.module_loading import import_string

        cfg = getattr(settings, "NINJA_BOOST", {})
        for dotted_path in cfg.get("PLUGINS", []):
            try:
                cls = import_string(dotted_path)
                instance = cls() if isinstance(cls, type) else cls
                self.register(instance)
            except Exception:
                logger.exception("Failed to load plugin '%s'", dotted_path)

    def __len__(self) -> int:
        return len(self._plugins)

    def __repr__(self) -> str:
        names = ", ".join(p.name for p in self._plugins)
        return f"<PluginRegistry [{names}]>"


# ── Global singleton ──────────────────────────────────────────────────────
plugin_registry = PluginRegistry()
