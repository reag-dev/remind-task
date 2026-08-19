from datetime import date, timedelta

import pytest
from django.urls import reverse
from freezegun import freeze_time

from records.models import Record
from tables.models import Column, ColumnType, Table

pytestmark = pytest.mark.django_db

TODAY = date(2026, 8, 19)
NOON = "2026-08-19T12:00:00Z"

# Client construído dentro do freeze_time: um JWT emitido antes do congelamento
# tem `iat` no futuro em relação ao relógio congelado e volta 401.


def rec_list(table_id):
    return reverse("records:record-list", args=[table_id])


@pytest.fixture
def scenario(db, user):
    """Um registro por status, criado fora de ordem de propósito."""
    table = Table.objects.create(user=user, name="Contratos", alert_lead_days=3)
    Column.objects.create(table=table, name="Vence", type=ColumnType.DUE_DATE, position=0)
    Column.objects.create(table=table, name="Cliente", type=ColumnType.TEXT, position=1)

    plan = [
        ("sem_data", None),
        ("em_dia", TODAY + timedelta(days=40)),
        ("vencido_antigo", TODAY - timedelta(days=20)),
        ("proximo", TODAY + timedelta(days=2)),
        ("hoje", TODAY),
        ("vencido_recente", TODAY - timedelta(days=1)),
    ]
    for label, due in plan:
        Record.objects.create(
            table=table,
            data={"vence": due.isoformat() if due else None, "cliente": label},
        )
    return table


def labels(response):
    return [row["data"]["cliente"] for row in response.data["results"]]


def fetch(authenticate, user, table, params=None):
    with freeze_time(NOON):
        return authenticate(user).get(rec_list(table.id), params or {})


# ---------------------------------------------------------------- RF11


def test_default_order_is_the_rf11_priority(authenticate, user, scenario):
    """
    Vencidos (mais antigo primeiro) → hoje → próximos → futuros → sem data.

    Sai de um único `ORDER BY due_date ASC` com NULL por último. Nenhuma lógica
    de status participa da ordenação.
    """
    response = fetch(authenticate, user, scenario)

    assert labels(response) == [
        "vencido_antigo",
        "vencido_recente",
        "hoje",
        "proximo",
        "em_dia",
        "sem_data",
    ]


def test_descending_order_still_keeps_nulls_last(authenticate, user, scenario):
    """
    O padrão do Postgres em DESC é NULL PRIMEIRO.

    Sem o NullsLastOrderingFilter, `?ordering=-due_date` abriria a lista com os
    registros sem vencimento — o oposto do que interessa.
    """
    response = fetch(authenticate, user, scenario, {"ordering": "-due_date"})

    assert labels(response) == [
        "em_dia",
        "proximo",
        "hoje",
        "vencido_recente",
        "vencido_antigo",
        "sem_data",
    ]


def test_manual_ordering_by_position(authenticate, user, scenario):
    """
    RF11 também pede ordenação manual.

    `position` é livre em registros — sem constraint de unicidade, ao contrário
    de colunas —, então cada um pode ser posicionado por um PATCH simples. Exigir
    a lista inteira de ids, como no reorder de colunas, não faria sentido aqui:
    uma tabela pode ter milhares de registros.
    """
    records = list(Record.objects.filter(table=scenario).order_by("created_at"))
    chosen = records[:3]

    with freeze_time(NOON):
        client = authenticate(user)
        for index, record in enumerate(reversed(chosen)):
            response = client.patch(
                reverse("records:record-detail", args=[scenario.id, record.id]),
                {"position": index},
                format="json",
            )
            assert response.status_code == 200, response.data
        listed = client.get(rec_list(scenario.id), {"ordering": "position"})

    positioned = [r.data["cliente"] for r in reversed(chosen)]
    assert labels(listed)[:3] == positioned
    # Quem nunca foi posicionado fica no fim, não no topo.
    assert len(labels(listed)) == 6


def test_ordering_by_a_field_outside_the_allow_list_is_ignored(
    authenticate, user, scenario
):
    """`?ordering=data` não pode virar ordenação por um campo não previsto."""
    response = fetch(authenticate, user, scenario, {"ordering": "data"})

    assert response.status_code == 200
    assert labels(response)[0] == "vencido_antigo"  # caiu no padrão


# ---------------------------------------------------------------- filtros


def test_filter_by_a_single_status(authenticate, user, scenario):
    response = fetch(authenticate, user, scenario, {"status": "overdue"})

    assert sorted(labels(response)) == ["vencido_antigo", "vencido_recente"]


def test_filter_by_several_statuses(authenticate, user, scenario):
    response = fetch(authenticate, user, scenario, {"status": "overdue,due_today"})

    assert sorted(labels(response)) == ["hoje", "vencido_antigo", "vencido_recente"]


def test_unknown_status_is_rejected_instead_of_returning_nothing(
    authenticate, user, scenario
):
    """
    Um status inexistente devolveria lista vazia se fosse ignorado, e o cliente
    concluiria "não há registros" em vez de "errei o filtro".
    """
    response = fetch(authenticate, user, scenario, {"status": "atrasadissimo"})

    assert response.status_code == 400
    assert "atrasadissimo" in str(response.data)


def test_filter_by_date_range(authenticate, user, scenario):
    response = fetch(
        authenticate, user, scenario, {"due_after": "2026-08-19", "due_before": "2026-08-25"}
    )

    assert sorted(labels(response)) == ["hoje", "proximo"]


def test_filter_records_without_due_date(authenticate, user, scenario):
    response = fetch(authenticate, user, scenario, {"has_due_date": "false"})

    assert labels(response) == ["sem_data"]
