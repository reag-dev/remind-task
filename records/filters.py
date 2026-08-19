from functools import reduce
from operator import or_

from django.db.models import F, Q
from django_filters import rest_framework as filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter

from core.dates import user_today
from records.models import Record
from records.status import DueStatus, status_filter_q


class RecordFilterBackend(DjangoFilterBackend):
    """
    Injeta no FilterSet o que o filtro de status precisa e ele não teria sozinho:
    a data de hoje no fuso do usuário e o `alert_lead_days` da tabela.

    O limiar é por tabela, mas a coleção já está delimitada a uma — então aqui ele
    é constante, e é isso que permite traduzir o status para uma faixa de datas
    fixa em vez de comparar contra uma coluna.
    """

    def get_filterset_kwargs(self, request, queryset, view):
        kwargs = super().get_filterset_kwargs(request, queryset, view)
        kwargs["table"] = view.get_table()
        kwargs["today"] = user_today(request.user)
        return kwargs


class NullsLastOrderingFilter(OrderingFilter):
    """
    OrderingFilter que sempre joga NULL para o fim.

    O padrão do Postgres é NULL por último em ASC e por PRIMEIRO em DESC. Sem
    isto, `?ordering=-due_date` abriria a lista com todos os registros sem
    vencimento — o oposto do que RF11 pede. Vale também para `position`: quem
    nunca foi posicionado manualmente vai para o fim, não para o topo.
    """

    def filter_queryset(self, request, queryset, view):
        ordering = self.get_ordering(request, queryset, view)
        if not ordering:
            return queryset
        return queryset.order_by(*[self._as_expression(term) for term in ordering])

    @staticmethod
    def _as_expression(term: str):
        if term.startswith("-"):
            return F(term[1:]).desc(nulls_last=True)
        return F(term).asc(nulls_last=True)


class RecordFilter(filters.FilterSet):
    status = filters.CharFilter(
        method="filter_status",
        help_text=(
            "Um ou mais status separados por vírgula: "
            + ", ".join(DueStatus.values)
        ),
    )
    due_before = filters.DateFilter(field_name="due_date", lookup_expr="lte")
    due_after = filters.DateFilter(field_name="due_date", lookup_expr="gte")
    has_due_date = filters.BooleanFilter(
        field_name="due_date", lookup_expr="isnull", exclude=True
    )

    class Meta:
        model = Record
        fields = ["status", "due_before", "due_after", "has_due_date"]

    def __init__(self, *args, table=None, today=None, **kwargs):
        self.table = table
        self.today = today
        super().__init__(*args, **kwargs)

    def filter_status(self, queryset, name, value):
        wanted = [item.strip() for item in value.split(",") if item.strip()]
        if not wanted:
            return queryset

        invalid = sorted(set(wanted) - set(DueStatus.values))
        if invalid:
            # Silenciar um status inexistente devolveria uma lista vazia e o
            # cliente concluiria "não há registros" em vez de "errei o filtro".
            raise ValidationError(
                {"status": f"Valor(es) inválido(s): {', '.join(invalid)}."}
            )

        # Faixa de datas em vez de `due_status__in`: filtrar pela anotação faria
        # o Postgres avaliar o CASE linha a linha e descartar o índice
        # (table_id, due_date). Ver status_filter_q.
        lead_days = self.table.alert_lead_days
        predicate = reduce(
            or_, (status_filter_q(status, self.today, lead_days) for status in wanted), Q()
        )
        return queryset.filter(predicate)
