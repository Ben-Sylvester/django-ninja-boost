from django.apps import AppConfig
from django.core.exceptions import ImproperlyConfigured


class NinjaBoostConfig(AppConfig):
    name = "ninja_boost"
    verbose_name = "Django Ninja Boost"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        user_config = self._get_user_config()
        if user_config is None:
            return  # all defaults — perfectly valid

        required = {"AUTH", "RESPONSE_WRAPPER", "PAGINATION", "DI"}
        missing = required - user_config.keys()
        if missing:
            raise ImproperlyConfigured(
                f"[ninja_boost] NINJA_BOOST settings is missing keys: {missing}. "
                "Run `ninja-boost config` for a starter block, or remove the "
                "partial config to use all defaults."
            )

    @staticmethod
    def _get_user_config():
        from django.conf import settings
        return getattr(settings, "NINJA_BOOST", None)


default_app_config = "ninja_boost.apps.NinjaBoostConfig"
