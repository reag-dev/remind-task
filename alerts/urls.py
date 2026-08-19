from django.urls import include, path
from rest_framework.routers import DefaultRouter

from alerts.views import AlertRuleViewSet, AlertViewSet

app_name = "alerts"

inbox_router = DefaultRouter()
inbox_router.register("alerts", AlertViewSet, basename="alert")

rules_router = DefaultRouter()
rules_router.register("alert-rules", AlertRuleViewSet, basename="alert-rule")

urlpatterns = [
    path("", include(inbox_router.urls)),
    path("tables/<uuid:table_id>/", include(rules_router.urls)),
]
