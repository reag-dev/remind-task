"""
Regra de status de vencimento (RF10), em Python.

Existe uma segunda implementação da MESMA regra em SQL
(`RecordQuerySet.with_due_status`), porque filtrar e ordenar por status precisa
acontecer no banco — não dá para paginar sobre um valor calculado em Python.

Duas implementações da mesma regra divergem com o tempo. A defesa é
`test_sql_and_python_agree_on_every_status`, que roda as duas sobre uma grade de
casos e exige resultado idêntico. Ao mexer aqui, mexa lá — o teste cobra.
"""

from datetime import date, timedelta

from django.db import models
from django.db.models import Q


class DueStatus(models.TextChoices):
    OVERDUE = "overdue", "Vencido"
    DUE_TODAY = "due_today", "Vence hoje"
    DUE_SOON = "due_soon", "Próximo do vencimento"
    ON_TRACK = "on_track", "Em dia"
    NO_DUE = "no_due", "Sem vencimento"


def due_status_for(due_date: date | None, today: date, lead_days: int) -> str:
    if due_date is None:
        return DueStatus.NO_DUE
    if due_date < today:
        return DueStatus.OVERDUE
    if due_date == today:
        return DueStatus.DUE_TODAY
    if (due_date - today).days <= lead_days:
        return DueStatus.DUE_SOON
    return DueStatus.ON_TRACK


def status_filter_q(status: str, today: date, lead_days: int) -> Q:
    """
    A mesma regra escrita como faixa de datas sobre `due_date`.

    Filtrar pela anotação `due_status` funcionaria, mas obrigaria o Postgres a
    avaliar o CASE linha a linha — o índice (table_id, due_date) fica de fora
    justamente no filtro mais usado, "mostre os vencidos". Traduzido para
    comparações diretas em `due_date`, o filtro volta a ser sargável e o
    planejador usa o índice.

    Terceira escrita da mesma regra, e por isso a mais arriscada:
    test_filter_predicates_match_the_annotation confere, para cada status, que o
    conjunto filtrado é idêntico ao conjunto anotado.
    """
    soon_limit = today + timedelta(days=lead_days)

    return {
        DueStatus.NO_DUE: Q(due_date__isnull=True),
        DueStatus.OVERDUE: Q(due_date__lt=today),
        DueStatus.DUE_TODAY: Q(due_date=today),
        # lead_days=0 torna esta faixa vazia, o que é correto: com antecedência
        # zero nada é "próximo" — hoje é due_today e amanhã já é on_track.
        DueStatus.DUE_SOON: Q(due_date__gt=today, due_date__lte=soon_limit),
        DueStatus.ON_TRACK: Q(due_date__gt=soon_limit),
    }[status]
