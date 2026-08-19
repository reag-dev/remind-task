from django.urls import include, path
from rest_framework.routers import DefaultRouter

from tables.views import ColumnViewSet, TableViewSet

app_name = "tables"

# Dois routers em vez de drf-nested-routers: uma dependência a menos para
# resolver `/api/tables/{table_id}/columns/`, que é o único aninhamento do MVP.
tables_router = DefaultRouter()
tables_router.register("tables", TableViewSet, basename="table")

columns_router = DefaultRouter()
columns_router.register("columns", ColumnViewSet, basename="column")

urlpatterns = [
    path("", include(tables_router.urls)),
    path("tables/<uuid:table_id>/", include(columns_router.urls)),
]
