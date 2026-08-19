from django.apps import AppConfig


class AlertsConfig(AppConfig):
    name = "alerts"
    verbose_name = "Alertas"

    def ready(self):
        # Os sinais vivem em `alerts` — e não em `tables`/`records` — para manter
        # a direção da dependência: alertas conhecem tabelas e registros, não o
        # contrário.
        from alerts import signals  # noqa: F401
