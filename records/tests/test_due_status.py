from datetime import date, timedelta

import pytest
from django.urls import reverse
from freezegun import freeze_time

from core.dates import user_today
from records.models import Record
from records.status import DueStatus, due_status_for, status_filter_q
from tables.models import Column, ColumnType, Table

pytestmark = pytest.mark.django_db

# 02:00 UTC: já é dia 20 em Tóquio (11h) e ainda é dia 19 em São Paulo (23h).
# Instante escolhido de propósito para separar "data do servidor" de "data do
# usuário" — em UTC seria 2026-08-20.
DAY_BOUNDARY = "2026-08-20T02:00:00Z"
NOON = "2026-08-19T12:00:00Z"

# Os testes chamam authenticate() DENTRO do bloco congelado, em vez de usar a
# fixture auth_client. Um JWT emitido antes do freeze_time nasce com `iat` no
# futuro em relação ao relógio congelado e o request volta 401.


def rec_list(table_id):
    return reverse("records:record-list", args=[table_id])


@pytest.fixture
def due_table(db, user):
    """Tabela com uma coluna de vencimento e limiar de 3 dias."""
    table = Table.objects.create(user=user, name="Vencimentos", alert_lead_days=3)
    Column.objects.create(table=table, name="Vence", type=ColumnType.DUE_DATE, position=0)
    return table


def make(table, due: date | None):
    return Record.objects.create(
        table=table, data={"vence": due.isoformat() if due else None}
    )


# ---------------------------------------------------------------- RF10


def test_the_five_statuses(authenticate, user, due_table):
    today = date(2026, 8, 19)
    expected = {
        "overdue": today - timedelta(days=1),
        "due_today": today,
        "due_soon": today + timedelta(days=3),      # exatamente no limiar
        "on_track": today + timedelta(days=4),      # um dia além
        "no_due": None,
    }
    ids = {status: str(make(due_table, due).id) for status, due in expected.items()}

    with freeze_time(NOON):
        response = authenticate(user).get(rec_list(due_table.id))

    got = {row["id"]: row["due_status"] for row in response.data["results"]}
    for status, record_id in ids.items():
        assert got[record_id] == status, f"esperava {status}"


def test_days_until_due_is_negative_when_overdue(authenticate, user, due_table):
    make(due_table, date(2026, 8, 14))

    with freeze_time(NOON):
        row = authenticate(user).get(rec_list(due_table.id)).data["results"][0]

    assert row["days_until_due"] == -5


def test_days_until_due_is_null_without_due_date(authenticate, user, due_table):
    make(due_table, None)

    with freeze_time(NOON):
        row = authenticate(user).get(rec_list(due_table.id)).data["results"][0]

    assert row["days_until_due"] is None


def test_the_soon_threshold_follows_the_table(authenticate, user):
    """RF10 diz que o período é configurável — o limiar é por tabela."""
    strict = Table.objects.create(user=user, name="Curta", alert_lead_days=1)
    generous = Table.objects.create(user=user, name="Longa", alert_lead_days=30)
    for table in (strict, generous):
        Column.objects.create(table=table, name="Vence", type=ColumnType.DUE_DATE, position=0)
        make(table, date(2026, 8, 29))  # 10 dias à frente

    with freeze_time(NOON):
        client = authenticate(user)
        strict_row = client.get(rec_list(strict.id)).data["results"][0]
        generous_row = client.get(rec_list(generous.id)).data["results"][0]

    assert strict_row["due_status"] == "on_track"
    assert generous_row["due_status"] == "due_soon"


# ---------------------------------------------------------------- fuso horário


def test_today_depends_on_the_user_timezone(user, other_user):
    user.timezone = "America/Sao_Paulo"
    other_user.timezone = "Asia/Tokyo"

    with freeze_time(DAY_BOUNDARY):
        assert user_today(user) == date(2026, 8, 19)
        assert user_today(other_user) == date(2026, 8, 20)


def test_the_same_due_date_reads_differently_in_two_timezones(
    authenticate, user, other_user
):
    """
    Dois usuários, o mesmo vencimento (2026-08-20), status diferentes.

    Para quem está em Tóquio já é dia 20: vence hoje. Para quem está em São Paulo
    ainda é dia 19: vence amanhã. Usar a data do SERVIDOR (UTC, dia 20) daria a
    resposta de Tóquio para os dois.
    """
    user.timezone = "America/Sao_Paulo"
    user.save(update_fields=["timezone"])
    other_user.timezone = "Asia/Tokyo"
    other_user.save(update_fields=["timezone"])

    for account in (user, other_user):
        table = Table.objects.create(user=account, name="Contratos", alert_lead_days=3)
        Column.objects.create(table=table, name="Vence", type=ColumnType.DUE_DATE, position=0)
        make(table, date(2026, 8, 20))

    rows = {}
    with freeze_time(DAY_BOUNDARY):
        for account in (user, other_user):
            table = Table.objects.get(user=account)
            response = authenticate(account).get(rec_list(table.id))
            rows[account.timezone] = response.data["results"][0]

    assert rows["America/Sao_Paulo"]["due_status"] == "due_soon"
    assert rows["America/Sao_Paulo"]["days_until_due"] == 1

    assert rows["Asia/Tokyo"]["due_status"] == "due_today"
    assert rows["Asia/Tokyo"]["days_until_due"] == 0


# ---------------------------------------------------------------- anti-deriva


def test_sql_and_python_agree_on_every_status(due_table):
    """
    Guarda contra deriva entre as duas implementações da regra de status.

    A anotação em SQL existe porque filtrar e ordenar precisa acontecer no banco;
    a função em Python existe porque a serialização de um objeto recém-criado não
    passa pela queryset. São dois códigos para a mesma regra — este teste roda os
    dois sobre a mesma grade e exige resultado idêntico.
    """
    today = date(2026, 8, 19)

    for offset in [-30, -2, -1, 0, 1, 2, 3, 4, 10, 400]:
        make(due_table, today + timedelta(days=offset))
    make(due_table, None)

    annotated = list(Record.objects.filter(table=due_table).with_due_status(today))

    for record in annotated:
        expected = due_status_for(record.due_date, today, due_table.alert_lead_days)
        assert record.due_status == expected, (
            f"due_date={record.due_date}: SQL disse {record.due_status}, "
            f"Python disse {expected}"
        )

    # A grade cobre os cinco status — senão o teste passaria sem provar nada.
    assert {r.due_status for r in annotated} == set(DueStatus.values)


@pytest.mark.parametrize("lead_days", [0, 1, 3, 30])
def test_filter_predicates_match_the_annotation(user, lead_days):
    """
    Terceira escrita da mesma regra: as faixas de data usadas no filtro.

    Existem para o `?status=` continuar sargável (usar o índice) em vez de
    obrigar o Postgres a avaliar o CASE linha a linha. Aqui cada faixa é
    confrontada com o conjunto que a anotação produz — se as duas discordarem em
    qualquer status ou qualquer limiar, o teste quebra.
    """
    today = date(2026, 8, 19)
    table = Table.objects.create(user=user, name=f"L{lead_days}", alert_lead_days=lead_days)
    Column.objects.create(table=table, name="Vence", type=ColumnType.DUE_DATE, position=0)

    for offset in [-10, -1, 0, 1, 2, 3, 4, 31, 400]:
        make(table, today + timedelta(days=offset))
    make(table, None)

    base = Record.objects.filter(table=table)
    annotated = base.with_due_status(today)

    for status in DueStatus.values:
        by_annotation = {r.id for r in annotated if r.due_status == status}
        by_predicate = set(
            base.filter(status_filter_q(status, today, lead_days)).values_list(
                "id", flat=True
            )
        )
        assert by_predicate == by_annotation, (
            f"status={status} lead_days={lead_days}: "
            f"filtro devolveu {len(by_predicate)}, anotação {len(by_annotation)}"
        )
