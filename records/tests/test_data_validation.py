import pytest
from django.db import IntegrityError, connection, transaction
from django.urls import reverse

from records.models import Record
from tables.models import Column, ColumnType

pytestmark = pytest.mark.django_db


def rec_list(table_id):
    return reverse("records:record-list", args=[table_id])


@pytest.fixture
def single_column(table):
    """Fábrica de tabela com uma coluna só — isola o tipo sob teste."""

    def _make(column_type, **kwargs):
        table.columns.all().delete()
        return Column.objects.create(
            table=table, name="Campo", type=column_type, position=0, **kwargs
        )

    return _make


def post(client, table, value):
    return client.post(rec_list(table.id), {"data": {"campo": value}}, format="json")


# ---------------------------------------------------------------- chaves


def test_unknown_key_is_rejected(auth_client, table, columns, valid_row):
    response = auth_client.post(
        rec_list(table.id), {"data": {**valid_row, "inventada": "x"}}, format="json"
    )

    assert response.status_code == 400
    assert "inventada" in str(response.data)


def test_missing_required_field_is_rejected(auth_client, table, columns):
    response = auth_client.post(
        rec_list(table.id), {"data": {"cliente": "Empresa A"}}, format="json"
    )

    assert response.status_code == 400
    assert "contrato" in str(response.data)


def test_optional_fields_become_null(auth_client, table, columns):
    response = auth_client.post(
        rec_list(table.id),
        {"data": {"contrato": "CT-1", "data_de_vencimento": "2026-08-20"}},
        format="json",
    )

    assert response.status_code == 201
    assert response.data["data"]["cliente"] is None


# ---------------------------------------------------------------- por tipo


@pytest.mark.parametrize(
    "column_type,value,expected",
    [
        (ColumnType.TEXT, "  Empresa  ", "Empresa"),
        (ColumnType.NUMBER, 42, 42),
        (ColumnType.NUMBER, "42", 42),
        (ColumnType.NUMBER, "3.5", 3.5),
        (ColumnType.NUMBER, -7, -7),
        (ColumnType.DATE, "2026-08-20", "2026-08-20"),
        (ColumnType.DATETIME, "2026-08-20T10:30:00", "2026-08-20T10:30:00"),
        (ColumnType.BOOLEAN, True, True),
        (ColumnType.BOOLEAN, False, False),
        (ColumnType.EMAIL, "  Alguem@Example.com ", "Alguem@Example.com"),
    ],
)
def test_accepted_values_are_normalized(
    auth_client, table, single_column, column_type, value, expected
):
    single_column(column_type)

    response = post(auth_client, table, value)

    assert response.status_code == 201, response.data
    assert response.data["data"]["campo"] == expected


@pytest.mark.parametrize(
    "column_type,value",
    [
        (ColumnType.NUMBER, "abc"),
        (ColumnType.NUMBER, True),          # booleano não é número
        (ColumnType.DATE, "20/08/2026"),    # formato brasileiro não é ISO
        (ColumnType.DATE, "2026-02-30"),    # data inexistente
        (ColumnType.DATETIME, "ontem"),
        (ColumnType.BOOLEAN, "true"),       # string não é booleano
        (ColumnType.BOOLEAN, 1),
        (ColumnType.EMAIL, "sem-arroba"),
        (ColumnType.TEXT, {"a": 1}),        # objeto aninhado não é texto
        (ColumnType.TEXT, ["a"]),
    ],
)
def test_rejected_values(auth_client, table, single_column, column_type, value):
    single_column(column_type)

    response = post(auth_client, table, value)

    assert response.status_code == 400, response.data
    assert "campo" in str(response.data)


def test_text_longer_than_the_cap_is_rejected(auth_client, table, single_column):
    single_column(ColumnType.TEXT)

    response = post(auth_client, table, "x" * 5_001)

    assert response.status_code == 400


def test_select_accepts_only_declared_options(auth_client, table, single_column):
    single_column(ColumnType.SELECT, options=["Ativo", "Encerrado"])

    assert post(auth_client, table, "Ativo").status_code == 201
    rejected = post(auth_client, table, "Suspenso")
    assert rejected.status_code == 400
    assert "Ativo" in str(rejected.data)  # a mensagem lista as opções válidas


# ---------------------------------------------------------------- due_date


def test_due_date_column_promotes_and_clears(auth_client, table, single_column):
    from datetime import date

    single_column(ColumnType.DUE_DATE)

    created = post(auth_client, table, "2026-09-01")
    record = Record.objects.get(id=created.data["id"])
    assert record.due_date == date(2026, 9, 1)

    auth_client.patch(
        reverse("records:record-detail", args=[table.id, record.id]),
        {"data": {"campo": None}},
        format="json",
    )
    record.refresh_from_db()
    assert record.due_date is None


def test_due_date_column_rejects_a_bad_date(auth_client, table, single_column):
    single_column(ColumnType.DUE_DATE)

    assert post(auth_client, table, "31/12/2026").status_code == 400


# ---------------------------------------------------------------- banco


def test_database_refuses_a_data_that_is_not_an_object(table):
    """
    O validador é a primeira barreira; a CHECK constraint é a segunda.

    Um update pelo ORM, um script de importação ou um INSERT manual poderiam
    gravar um array no lugar do objeto — todo o resto do sistema assume objeto.
    """
    record = Record.objects.create(table=table, data={})

    with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            "UPDATE records SET data = %s::jsonb WHERE id = %s",
            ["[1,2,3]", str(record.id)],
        )
