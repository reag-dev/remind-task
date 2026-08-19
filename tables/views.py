from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from tables.models import Column, Table
from tables.serializers import ColumnSerializer, ReorderSerializer, TableSerializer


@extend_schema_view(
    list=extend_schema(tags=["tables"], summary="Lista as tabelas da conta (RF04)"),
    retrieve=extend_schema(tags=["tables"], summary="Detalha uma tabela com suas colunas"),
    create=extend_schema(tags=["tables"], summary="Cria uma tabela (RF03)"),
    update=extend_schema(tags=["tables"], summary="Substitui uma tabela"),
    partial_update=extend_schema(tags=["tables"], summary="Atualiza uma tabela"),
    destroy=extend_schema(tags=["tables"], summary="Exclui uma tabela e tudo dentro dela"),
)
class TableViewSet(viewsets.ModelViewSet):
    serializer_class = TableSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # O drf-spectacular instancia a view sem request autenticada para inferir
        # o schema; sem esta guarda o filtro por user estoura com AnonymousUser.
        if getattr(self, "swagger_fake_view", False):
            return Table.objects.none()

        # RS01/RS04: NUNCA Table.objects.all(). Trocar o id na URL para o de
        # outra conta não encontra a linha — a resposta é 404, não 403, para não
        # confirmar que o recurso existe.
        return (
            Table.objects.filter(user=self.request.user)
            .prefetch_related("columns")
            .order_by("-created_at")
        )

    def perform_create(self, serializer):
        # O dono vem do token, nunca do corpo da requisição.
        serializer.save(user=self.request.user)


@extend_schema_view(
    list=extend_schema(tags=["columns"], summary="Lista as colunas da tabela (RF05)"),
    retrieve=extend_schema(tags=["columns"], summary="Detalha uma coluna"),
    create=extend_schema(tags=["columns"], summary="Adiciona uma coluna (RF05, RF06)"),
    update=extend_schema(tags=["columns"], summary="Substitui uma coluna"),
    partial_update=extend_schema(tags=["columns"], summary="Renomeia ou reconfigura uma coluna"),
    destroy=extend_schema(tags=["columns"], summary="Remove uma coluna"),
)
class ColumnViewSet(viewsets.ModelViewSet):
    serializer_class = ColumnSerializer
    permission_classes = [IsAuthenticated]

    def get_table(self) -> Table:
        """
        Resolve a tabela-mãe já filtrada pelo dono, com cache por request.

        Chamado em TODA ação, inclusive no `list`. Sem isso, listar as colunas de
        uma tabela alheia devolveria 200 com lista vazia — nenhum dado vaza, mas
        a resposta difere de `create`, que dá 404. Uma coleção aninhada sob um
        recurso que você não pode ver simplesmente não existe: 404 sempre.
        """
        if not hasattr(self, "_table"):
            self._table = get_object_or_404(
                Table, pk=self.kwargs["table_id"], user=self.request.user
            )
        return self._table

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Column.objects.none()
        return Column.objects.filter(table=self.get_table()).order_by("position")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.action in {"create", "reorder"}:
            context["table"] = self.get_table()
        return context

    @extend_schema(
        tags=["columns"],
        summary="Reordena as colunas da tabela",
        description=(
            "Recebe os ids de todas as colunas na ordem desejada e reatribui as "
            "posições numa única transação. A constraint de posição é DEFERRABLE, "
            "então os estados intermediários duplicados não quebram nada."
        ),
        request=ReorderSerializer,
        responses={200: ColumnSerializer(many=True)},
    )
    @action(detail=False, methods=["patch"])
    def reorder(self, request, table_id=None):
        table = self.get_table()
        serializer = ReorderSerializer(
            data=request.data, context={"table": table, "request": request}
        )
        serializer.is_valid(raise_exception=True)

        ordered_ids = serializer.validated_data["order"]
        by_id = {column.id: column for column in table.columns.all()}

        with transaction.atomic():
            for position, column_id in enumerate(ordered_ids):
                by_id[column_id].position = position
            Column.objects.bulk_update(by_id.values(), ["position"])
            # A unicidade de (table, position) é conferida aqui, no COMMIT.

        return Response(
            ColumnSerializer(table.columns.order_by("position"), many=True).data,
            status=status.HTTP_200_OK,
        )
