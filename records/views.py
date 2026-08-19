import logging

from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from core.dates import user_today
from exports.services import ALLOWED_DELIMITERS, filename_for, stream_rows
from records.filters import NullsLastOrderingFilter, RecordFilter, RecordFilterBackend
from records.models import Record
from records.serializers import RecordSerializer
from records.status import DueStatus
from tables.models import Table

logger = logging.getLogger(__name__)

ORDERING_DESCRIPTION = (
    "Campo de ordenação. Prefixo `-` inverte. Valores aceitos: "
    "`due_date`, `created_at`, `updated_at`, `position`. "
    "NULL sempre por último. Padrão: `due_date,created_at`, que já produz a "
    "ordem do RF11 — vencidos, hoje, próximos, futuros, sem vencimento."
)


@extend_schema_view(
    list=extend_schema(
        tags=["records"],
        summary="Lista os registros da tabela (RF10, RF11)",
        parameters=[
            OpenApiParameter(
                "status",
                description="Filtra por status, separados por vírgula. Ex.: `overdue,due_today`.",
                enum=DueStatus.values,
            ),
            OpenApiParameter("ordering", description=ORDERING_DESCRIPTION),
        ],
    ),
    retrieve=extend_schema(tags=["records"], summary="Detalha um registro"),
    create=extend_schema(tags=["records"], summary="Insere um registro (RF07)"),
    update=extend_schema(tags=["records"], summary="Substitui um registro (RF08)"),
    partial_update=extend_schema(tags=["records"], summary="Atualiza um registro (RF08)"),
    destroy=extend_schema(tags=["records"], summary="Exclui um registro (RF09)"),
)
class RecordViewSet(viewsets.ModelViewSet):
    serializer_class = RecordSerializer
    permission_classes = [IsAuthenticated]

    filter_backends = [RecordFilterBackend, NullsLastOrderingFilter]
    filterset_class = RecordFilter
    ordering_fields = ["due_date", "created_at", "updated_at", "position"]
    # RF11: `due_date` ASC com NULL por último já entrega vencidos (mais antigo
    # primeiro) → hoje → próximos → futuros → sem data. Um índice resolve.
    ordering = ["due_date", "created_at"]

    def get_table(self) -> Table:
        if not hasattr(self, "_table"):
            self._table = get_object_or_404(
                Table.objects.prefetch_related("columns"),
                pk=self.kwargs["table_id"],
                user=self.request.user,
            )
        return self._table

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Record.objects.none()

        # Duplo filtro de propósito: `user` é a checagem de dono (RS01) e
        # `table` delimita a coleção. Mesmo que a tabela-mãe fosse resolvida
        # errado, o filtro por usuário ainda seguraria.
        return (
            Record.objects.filter(table=self.get_table(), user=self.request.user)
            .select_related("table")
            # Anotado ANTES dos filter backends: é o que permite `?status=` e
            # `?ordering=` operarem sobre o status calculado.
            .with_due_status(user_today(self.request.user))
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if getattr(self, "swagger_fake_view", False):
            return context

        table = self.get_table()
        context["table"] = table
        # Uma query só para as colunas, reaproveitada por todos os registros da
        # página — sem isso a validação faria N+1 num POST em lote.
        context["columns"] = list(table.columns.all())
        # "Hoje" resolvido uma vez por request: garante que todos os registros da
        # página sejam avaliados contra a mesma data, mesmo virando o dia no meio.
        context["today"] = user_today(self.request.user)
        return context

    @extend_schema(
        tags=["records"],
        summary="Exporta a tabela em CSV (RF13)",
        description=(
            "Exporta exatamente o que a listagem devolveria: os mesmos filtros "
            "(`?status=`, `?due_before=`…) e a mesma ordenação valem aqui. "
            "Colunas na ordem definida na tabela, com os rótulos como cabeçalho."
        ),
        parameters=[
            OpenApiParameter(
                "delimiter",
                description="`,` (padrão) ou `;` — Excel em pt-BR costuma esperar `;`.",
                enum=sorted(ALLOWED_DELIMITERS),
            )
        ],
        responses={(200, "text/csv"): OpenApiTypes.BINARY},
    )
    @action(detail=False, methods=["get"])
    def export(self, request, table_id=None):
        """
        RS08 — a exportação NÃO tem caminho de consulta próprio.

        É uma ação do próprio RecordViewSet, então usa literalmente o mesmo
        `get_queryset()` e o mesmo `filter_queryset()` da listagem. Uma view
        separada que refizesse `get_object_or_404(Table, ...)` seria um segundo
        lugar onde esquecer o filtro por dono — exatamente o risco que o
        requisito quer eliminar.
        """
        table = self.get_table()
        columns = list(table.columns.all())
        queryset = self.filter_queryset(self.get_queryset())

        today = user_today(request.user)
        filename = filename_for(table, today)

        response = StreamingHttpResponse(
            stream_rows(
                table, columns, queryset, delimiter=request.query_params.get("delimiter", ",")
            ),
            content_type="text/csv; charset=utf-8",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'

        # RS05 — só identificadores e contagem. Nunca conteúdo de célula.
        logger.info(
            "Exportação CSV: tabela=%s colunas=%s", table.id, len(columns)
        )
        return response
