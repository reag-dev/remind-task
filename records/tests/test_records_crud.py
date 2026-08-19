from datetime import date

import pytest
from django.urls import reverse

from records.models import Record

pytestmark = pytest.mark.django_db


def rec_list(table_id):
    return reverse("records:record-list", args=[table_id])


def rec_detail(table_id, record_id):
    return reverse("records:record-detail", args=[table_id, record_id])


# ---------------------------------------------------------------- RF07 inserção


def test_create_record(auth_client, table, columns, valid_row):
    response = auth_client.post(rec_list(table.id), {"data": valid_row}, format="json")

    assert response.status_code == 201
    assert response.data["data"]["cliente"] == "Empresa A"


def test_create_derives_the_owner_from_the_table(auth_client, table, columns, valid_row, user):
    response = auth_client.post(rec_list(table.id), {"data": valid_row}, format="json")

    record = Record.objects.get(id=response.data["id"])
    assert record.user == user


def test_create_promotes_the_due_date_from_the_json(auth_client, table, columns, valid_row):
    response = auth_client.post(rec_list(table.id), {"data": valid_row}, format="json")

    record = Record.objects.get(id=response.data["id"])
    assert record.due_date == date(2026, 8, 20)
    assert response.data["due_date"] == "2026-08-20"


def test_due_date_is_read_only_in_the_payload(auth_client, table, columns, valid_row):
    """Mandar due_date direto não pode fazê-lo divergir do JSONB."""
    response = auth_client.post(
        rec_list(table.id),
        {"data": valid_row, "due_date": "1999-01-01"},
        format="json",
    )

    assert Record.objects.get(id=response.data["id"]).due_date == date(2026, 8, 20)


def test_table_without_due_date_column_leaves_it_null(auth_client, table):
    from tables.models import Column, ColumnType

    Column.objects.create(table=table, name="Nota", type=ColumnType.TEXT, position=0)

    response = auth_client.post(rec_list(table.id), {"data": {"nota": "oi"}}, format="json")

    assert response.status_code == 201
    assert Record.objects.get(id=response.data["id"]).due_date is None


# ---------------------------------------------------------------- RF08 edição


def test_patch_merges_with_the_existing_data(auth_client, table, columns, record):
    response = auth_client.patch(
        rec_detail(table.id, record.id), {"data": {"cliente": "Empresa Z"}}, format="json"
    )

    assert response.status_code == 200
    record.refresh_from_db()
    assert record.data["cliente"] == "Empresa Z"
    assert record.data["contrato"] == "CT-001"  # não foi apagado pelo merge


def test_patch_that_empties_a_required_field_is_rejected(auth_client, table, columns, record):
    """
    O merge é o que torna esta checagem possível.

    Olhando só o delta, apagar um campo obrigatório passaria — `contrato` não
    estaria no payload e nada seria conferido.
    """
    response = auth_client.patch(
        rec_detail(table.id, record.id), {"data": {"contrato": ""}}, format="json"
    )

    assert response.status_code == 400
    assert "contrato" in str(response.data)


def test_patch_updates_the_promoted_due_date(auth_client, table, columns, record):
    auth_client.patch(
        rec_detail(table.id, record.id),
        {"data": {"data_de_vencimento": "2027-01-15"}},
        format="json",
    )

    record.refresh_from_db()
    assert record.due_date == date(2027, 1, 15)


# ---------------------------------------------------------------- RF09 exclusão


def test_delete_record(auth_client, table, columns, record):
    assert auth_client.delete(rec_detail(table.id, record.id)).status_code == 204
    assert not Record.objects.filter(id=record.id).exists()


def test_deleting_a_table_deletes_its_records(auth_client, table, record):
    auth_client.delete(reverse("tables:table-detail", args=[table.id]))

    assert not Record.objects.filter(id=record.id).exists()


# ---------------------------------------------------------------- leitura


def test_list_returns_only_records_of_the_requested_table(
    auth_client, table, columns, record, other_record
):
    response = auth_client.get(rec_list(table.id))

    assert response.status_code == 200
    assert [row["id"] for row in response.data["results"]] == [str(record.id)]


def test_list_orders_by_due_date_with_nulls_last(auth_client, table, columns):
    """RF11 sai de um único ORDER BY due_date ASC — NULL fica por último."""
    Record.objects.create(table=table, data={**_row("2026-12-01"), "cliente": "futuro"})
    Record.objects.create(table=table, data={**_row("2026-01-01"), "cliente": "vencido"})
    Record.objects.create(table=table, data={**_row(None), "cliente": "sem data"})

    response = auth_client.get(rec_list(table.id))

    assert [r["data"]["cliente"] for r in response.data["results"]] == [
        "vencido",
        "futuro",
        "sem data",
    ]


def _row(due):
    return {
        "cliente": "x",
        "contrato": "CT",
        "responsavel": "y",
        "data_de_vencimento": due,
        "status": "Ativo",
    }


# ---------------------------------------------------------------- RS01 / RS04


def test_cannot_list_records_of_another_users_table(auth_client, other_table):
    assert auth_client.get(rec_list(other_table.id)).status_code == 404


def test_cannot_create_a_record_in_another_users_table(auth_client, other_table):
    response = auth_client.post(rec_list(other_table.id), {"data": {}}, format="json")

    assert response.status_code == 404
    assert not Record.objects.filter(table=other_table).exists()


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_cannot_touch_another_users_record(auth_client, other_table, other_record, method):
    url = rec_detail(other_table.id, other_record.id)
    call = getattr(auth_client, method)
    response = call(url, {}, format="json") if method == "patch" else call(url)

    assert response.status_code == 404
    assert Record.objects.filter(id=other_record.id).exists()


def test_cannot_reach_a_foreign_record_through_your_own_table(
    auth_client, table, other_record
):
    """Id de registro alheio sob a SUA tabela também não passa."""
    assert auth_client.get(rec_detail(table.id, other_record.id)).status_code == 404


def test_records_require_authentication(api_client, table):
    assert api_client.get(rec_list(table.id)).status_code == 401
