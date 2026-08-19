from django.urls import include, path
from rest_framework.routers import DefaultRouter

from records.views import RecordViewSet

app_name = "records"

records_router = DefaultRouter()
records_router.register("records", RecordViewSet, basename="record")

urlpatterns = [
    path("tables/<uuid:table_id>/", include(records_router.urls)),
]
