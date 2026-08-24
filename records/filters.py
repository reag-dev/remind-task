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
from tables.models import ColumnType


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


#: Tipos de coluna que a busca textual varre.
#:
#: `text` e `email` são texto livre — é onde alguém digita o que depois vai
#: querer procurar. `select` fica de fora por ser domínio fechado: os valores
#: possíveis já são conhecidos e merecem filtro por igualdade, não `ILIKE`.
#: `number`, `date`, `datetime`, `boolean` e `due_date` também ficam de fora —
#: procurar "2026" como substring de data casaria o ano em registros que o
#: usuário não pediu, e existem `due_before`/`due_after` para isso.
#:
#: A lista é explícita de propósito: um tipo novo em ColumnType não entra na
#: busca por acidente, entra por decisão de quem o acrescentar.
SEARCHABLE_TYPES = frozenset({ColumnType.TEXT, ColumnType.EMAIL})


class RecordFilter(filters.FilterSet):
    q = filters.CharFilter(
        method="filter_search",
        help_text=(
            "Busca por substring, sem diferenciar maiúsculas. Varre apenas as "
            "colunas de texto e e-mail da tabela; colunas marcadas como "
            "sensíveis ficam de fora."
        ),
    )
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
        fields = ["q", "status", "due_before", "due_after", "has_due_date"]

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

    def filter_search(self, queryset, name, value):
        """
        Busca por substring nas colunas de texto da tabela.

        A coleção já está delimitada a uma tabela, então a lista de colunas é
        conhecida e curta — o OR é montado sobre ela, não sobre o JSON inteiro.

        **Colunas `is_sensitive` ficam de fora, e isso é segurança, não zelo.**
        A UI mascara esses valores (`CelulaValor.tsx`); deixá-los pesquisáveis
        devolveria o valor por tentativa e erro — quem busca `123`, depois
        `1234`, e observa quando o registro some, leu o campo mascarado sem
        nunca vê-lo. O mascaramento viraria enfeite.
        """
        termo = value.strip()
        if not termo:
            return queryset

        columns = [
            column
            for column in self.table.columns.all()
            if column.type in SEARCHABLE_TYPES and not column.is_sensitive
        ]

        # Sem coluna pesquisável, `none()` — não o queryset intacto. Devolver
        # tudo faria a busca parecer ter casado com a tabela inteira; a lista
        # vazia diz a verdade, que é "não há onde procurar".
        if not columns:
            return queryset.none()

        return queryset.filter(
            reduce(
                or_,
                (Q(**{f"data__{column.key}__icontains": termo}) for column in columns),
            )
        )
