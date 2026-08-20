from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "core"
    verbose_name = "Core"

    def ready(self):
        # Registra as extensões de securityScheme do drf-spectacular. O import
        # é o efeito colateral: as classes se auto-registram ao serem definidas.
        from core import schema  # noqa: F401
