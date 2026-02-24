"""
ninja_boost.apps
~~~~~~~~~~~~~~~~
Django AppConfig that validates settings and auto-loads plugins, policies,
services, and event bus wire-ups on startup.
"""

import logging

from django.apps import AppConfig
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger("ninja_boost.startup")

# Core keys that must be dotted-path strings if NINJA_BOOST is provided
_IMPORT_KEYS = {"AUTH", "RESPONSE_WRAPPER", "PAGINATION", "DI"}


class NinjaBoostConfig(AppConfig):
    name = "ninja_boost"
    verbose_name = "Django Ninja Boost"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from django.conf import settings

        user_config = getattr(settings, "NINJA_BOOST", None)

        if user_config is not None:
            self._validate_core_keys(user_config)

        # Auto-load plugins, policies, services from settings
        self._load_plugins()
        self._load_policies()
        self._load_services()

        # Auto-register health checks
        self._load_health_checks()

        # Wire default event bus handlers (access log, metrics)
        self._wire_default_handlers()

        logger.info("django-ninja-boost ready")


    # ── Validation ────────────────────────────────────────────────────────

    @staticmethod
    def _validate_core_keys(cfg: dict) -> None:
        """If any core key is provided, all four must be present."""
        provided_core = _IMPORT_KEYS & cfg.keys()
        if provided_core and not _IMPORT_KEYS.issubset(cfg.keys()):
            missing = _IMPORT_KEYS - cfg.keys()
            raise ImproperlyConfigured(
                f"[ninja_boost] NINJA_BOOST is missing required keys: {missing}. "
                "Provide all four (AUTH, RESPONSE_WRAPPER, PAGINATION, DI) or "
                "remove the partial config to use all defaults. "
                "Run `ninja-boost config` for a starter block."
            )

    # ── Auto-load ─────────────────────────────────────────────────────────

    @staticmethod
    def _load_plugins() -> None:
        try:
            from ninja_boost.plugins import plugin_registry
            plugin_registry.load_from_settings()
        except Exception:
            logger.exception("Failed to load plugins from settings")

    @staticmethod
    def _load_policies() -> None:
        try:
            from ninja_boost.policies import policy_registry
            policy_registry.load_from_settings()
        except Exception:
            logger.exception("Failed to load policies from settings")

    @staticmethod
    def _load_services() -> None:
        try:
            from ninja_boost.services import service_registry
            service_registry.load_from_settings()
        except Exception:
            logger.exception("Failed to load services from settings")

    @staticmethod
    def _load_health_checks() -> None:
        try:
            from django.conf import settings
            from ninja_boost.health import register_builtin_checks
            cfg = getattr(settings, "NINJA_BOOST", {})
            auto = cfg.get("HEALTH", {}).get("AUTO_CHECKS", ["database"])
            if auto:
                register_builtin_checks(auto)
        except Exception:
            logger.exception("Failed to register health checks")

    # ── Default event handlers ────────────────────────────────────────────

    @staticmethod
    def _wire_default_handlers() -> None:
        """
        Wire built-in event handlers that should always run.
        These are low-overhead and safe to enable unconditionally.
        """
        try:
            from ninja_boost.events import event_bus, AFTER_RESPONSE, ON_ERROR
            from ninja_boost.logging_structured import bind_request_context, BEFORE_REQUEST  # noqa: F401

            # Structured logging: bind context on every request
            from ninja_boost.events import BEFORE_REQUEST as BR

            @event_bus.on(BR)
            def _bind_log_ctx(request, ctx, **kw):
                try:
                    from ninja_boost.logging_structured import bind_request_context as _brc
                    _brc(request, ctx)
                except Exception:
                    pass

            # Metrics: track request completion
            @event_bus.on(AFTER_RESPONSE)
            def _track_metrics(request, ctx, response, duration_ms, **kw):
                try:
                    from ninja_boost.metrics import metrics
                    metrics.track_request_end(
                        method=getattr(request, "method", "?"),
                        path=getattr(request, "path", "/"),
                        status=getattr(response, "status_code", 200) if response else 200,
                        duration_ms=duration_ms,
                    )
                except Exception:
                    pass

            # Metrics: count unhandled errors
            @event_bus.on(ON_ERROR)
            def _track_error(request, ctx, exc, **kw):
                try:
                    from ninja_boost.metrics import metrics
                    metrics.increment("unhandled_errors_total",
                                      labels={"error_type": type(exc).__name__})
                except Exception:
                    pass

        except Exception:
            logger.debug("Default event handler wiring failed", exc_info=True)


default_app_config = "ninja_boost.apps.NinjaBoostConfig"
