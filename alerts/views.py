from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from alerts.models import Alert, AlertRule, AlertStatus
from alerts.serializers import AlertRuleSerializer, AlertSerializer
from tables.models import Table


@extend_schema_view(
    list=extend_schema(
        tags=["alerts"],
        summary="Caixa de entrada de alertas (RF12)",
        description="Somente os alertas do usuário autenticado, mais recentes primeiro.",
    ),
    retrieve=extend_schema(tags=["alerts"], summary="Detalha um alerta"),
)
class AlertViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Leitura + duas transições. Alertas nascem do job, nunca de um POST."""

    serializer_class = AlertSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["status"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Alert.objects.none()

        return (
            Alert.objects.filter(user=self.request.user)
            .select_related("record", "record__table")
            # As colunas alimentam o rótulo seguro do registro; sem o prefetch
            # cada alerta da página faria a sua própria query.
            .prefetch_related("record__table__columns")
            .order_by("-trigger_date", "-created_at")
        )

    def _transition(self, request, new_status, timestamp_field=None):
        alert = self.get_object()
        alert.status = new_status
        fields = ["status", "updated_at"]
        if timestamp_field and getattr(alert, timestamp_field) is None:
            setattr(alert, timestamp_field, timezone.now())
            fields.append(timestamp_field)
        alert.save(update_fields=fields)
        return Response(self.get_serializer(alert).data)

    @extend_schema(
        tags=["alerts"],
        summary="Marca como lido",
        request=None,
        responses={200: AlertSerializer},
    )
    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        return self._transition(request, AlertStatus.READ, "read_at")

    @extend_schema(
        tags=["alerts"],
        summary="Descarta o alerta",
        description="Sai da caixa de entrada sem apagar o histórico.",
        request=None,
        responses={200: AlertSerializer},
    )
    @action(detail=True, methods=["post"])
    def dismiss(self, request, pk=None):
        return self._transition(request, AlertStatus.DISMISSED)


@extend_schema_view(
    list=extend_schema(tags=["alert-rules"], summary="Regras de alerta da tabela"),
    retrieve=extend_schema(tags=["alert-rules"], summary="Detalha uma regra"),
    create=extend_schema(tags=["alert-rules"], summary="Cria uma regra de antecedência"),
    update=extend_schema(tags=["alert-rules"], summary="Substitui uma regra"),
    partial_update=extend_schema(tags=["alert-rules"], summary="Atualiza uma regra"),
    destroy=extend_schema(
        tags=["alert-rules"],
        summary="Remove uma regra",
        responses={204: OpenApiResponse(description="Regra removida com os alertas dela.")},
    ),
)
class AlertRuleViewSet(viewsets.ModelViewSet):
    serializer_class = AlertRuleSerializer
    permission_classes = [IsAuthenticated]

    def get_table(self) -> Table:
        if not hasattr(self, "_table"):
            self._table = get_object_or_404(
                Table, pk=self.kwargs["table_id"], user=self.request.user
            )
        return self._table

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return AlertRule.objects.none()
        return AlertRule.objects.filter(table=self.get_table()).order_by("-offset_days")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if not getattr(self, "swagger_fake_view", False):
            context["table"] = self.get_table()
        return context
