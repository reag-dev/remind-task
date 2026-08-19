from django.contrib import admin

from tables.models import Column, Table


class ColumnInline(admin.TabularInline):
    model = Column
    extra = 0
    readonly_fields = ("id", "key", "created_at", "updated_at")
    fields = ("position", "name", "key", "type", "is_required", "is_sensitive", "options")
    ordering = ("position",)


@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "alert_lead_days", "created_at")
    list_filter = ("alert_lead_days",)
    search_fields = ("name", "user__email")
    readonly_fields = ("id", "created_at", "updated_at")
    autocomplete_fields = ("user",)
    inlines = [ColumnInline]


@admin.register(Column)
class ColumnAdmin(admin.ModelAdmin):
    list_display = ("key", "name", "type", "table", "position", "is_required", "is_sensitive")
    list_filter = ("type", "is_required", "is_sensitive")
    search_fields = ("key", "name", "table__name")
    readonly_fields = ("id", "key", "created_at", "updated_at")
