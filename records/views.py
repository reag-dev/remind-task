from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from records.models import Record
from records.serializers import RecordSerializer
from tables.models import Table


@extend_schema_view(
    list=extend_schema(tags=["records"], summary="Lista os registros da tabela"),
    retrieve=extend_schema(tags=["records"], summary="Detalha um registro"),
    create=extend_schema(tags=["records"], summary="Insere um registro (RF07)"),
    update=extend_schema(tags=["records"], summary="Substitui um registro (RF08)"),
    partial_update=extend_schema(tags=["records"], summary="Atualiza um registro (RF08)"),
    destroy=extend_schema(tags=["records"], summary="Exclui um registro (RF09)"),
)
class RecordViewSet(viewsets.ModelViewSet):
    serializer_class = RecordSerializer
    permission_classes = [IsAuthenticated]

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
            .order_by("due_date", "created_at")
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
        return context
