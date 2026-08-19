"""
Dívida herdada da Phase 2: excluir uma coluna precisa limpar a chave dela no
JSONB de todos os registros. Só deu para implementar aqui, porque a tabela
`records` não existia antes.
"""

import pytest
from django.urls import reverse

from records.models import Record

pytestmark = pytest.mark.django_db


def col_detail(table_id, column_id):
    return reverse("tables:column-detail", args=[table_id, column_id])


def test_deleting_a_column_purges_its_key_from_every_record(
    auth_client, table, columns, valid_row
):
    a = Record.objects.create(table=table, data=dict(valid_row))
    b = Record.objects.create(table=table, data=dict(valid_row))
    cliente = columns[0]

    response = auth_client.delete(col_detail(table.id, cliente.id))

    assert response.status_code == 204
    for record in (a, b):
        record.refresh_from_db()
        assert "cliente" not in record.data
        # As outras chaves seguem intactas.
        assert record.data["contrato"] == "CT-001"


def test_purge_does_not_touch_records_of_other_tables(
    auth_client, table, columns, valid_row, other_table
):
    mine = Record.objects.create(table=table, data=dict(valid_row))
    theirs = Record.objects.create(table=other_table, data={"cliente": "intacto"})

    auth_client.delete(col_detail(table.id, columns[0].id))

    mine.refresh_from_db()
    theirs.refresh_from_db()
    assert "cliente" not in mine.data
    assert theirs.data["cliente"] == "intacto"


def test_deleting_the_due_date_column_also_clears_the_promoted_column(
    auth_client, table, columns, valid_row
):
    """
    Sem isto, `records.due_date` guardaria um vencimento sem origem e o job de
    alertas (RF12) continuaria disparando por ele.
    """
    record = Record.objects.create(table=table, data=dict(valid_row))
    assert record.due_date is not None

    due_column = next(c for c in columns if c.type == "due_date")
    auth_client.delete(col_detail(table.id, due_column.id))

    record.refresh_from_db()
    assert record.due_date is None
    assert "data_de_vencimento" not in record.data


def test_deleting_a_regular_column_keeps_the_due_date(
    auth_client, table, columns, valid_row
):
    record = Record.objects.create(table=table, data=dict(valid_row))

    auth_client.delete(col_detail(table.id, columns[0].id))

    record.refresh_from_db()
    assert record.due_date is not None
