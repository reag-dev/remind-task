from django.contrib import admin

from records.models import Record


@admin.register(Record)
class RecordAdmin(admin.ModelAdmin):
    list_display = ("id", "table", "user", "due_date", "created_at")
    list_filter = ("due_date",)
    search_fields = ("table__name", "user__email")
    # `data` fica somente leitura: editar o JSONB pelo admin pula o validador e
    # é o caminho mais fácil para gravar um valor que a API depois recusa.
    readonly_fields = ("id", "data", "due_date", "created_at", "updated_at")
    autocomplete_fields = ("table",)
