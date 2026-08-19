from django.contrib import admin

from alerts.models import Alert, AlertRule


@admin.register(AlertRule)
class AlertRuleAdmin(admin.ModelAdmin):
    list_display = ("table", "offset_days", "channel", "is_active", "user")
    list_filter = ("channel", "is_active")
    search_fields = ("table__name", "user__email")
    readonly_fields = ("id", "created_at", "updated_at")
    autocomplete_fields = ("table",)


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ("trigger_date", "due_date_snapshot", "status", "user", "notified_at")
    list_filter = ("status", "trigger_date")
    search_fields = ("user__email",)
    # Tudo somente leitura: alertas são gerados pelo job. Editar à mão aqui
    # produziria estado que a varredura não sabe reproduzir.
    readonly_fields = (
        "id", "record", "rule", "user", "trigger_date", "due_date_snapshot",
        "status", "notified_at", "read_at", "created_at", "updated_at",
    )

    def has_add_permission(self, request):
        return False
