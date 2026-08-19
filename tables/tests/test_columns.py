import pytest
from django.db import IntegrityError, transaction
from django.urls import reverse

from tables.models import Column, ColumnType

pytestmark = pytest.mark.django_db


def col_list(table_id):
    return reverse("tables:column-list", args=[table_id])


def col_detail(table_id, column_id):
    return reverse("tables:column-detail", args=[table_id, column_id])


def reorder_url(table_id):
    return reverse("tables:column-reorder", args=[table_id])


# ---------------------------------------------------------------- RF05 criação


def test_create_column_derives_a_slug_key_from_the_name(auth_client, table):
    response = auth_client.post(
        col_list(table.id), {"name": "Data de Vencimento", "type": "text"}, format="json"
    )

    assert response.status_code == 201
    assert response.data["key"] == "data_de_vencimento"


def test_key_falls_back_when_the_name_has_no_slug(auth_client, table):
    response = auth_client.post(
        col_list(table.id), {"name": "***", "type": "text"}, format="json"
    )

    assert response.status_code == 201
    assert response.data["key"] == "coluna"


def test_colliding_names_get_distinct_keys(auth_client, table):
    first = auth_client.post(col_list(table.id), {"name": "Status", "type": "text"}, format="json")
    second = auth_client.post(col_list(table.id), {"name": "status", "type": "text"}, format="json")

    assert first.data["key"] == "status"
    assert second.data["key"] == "status_2"


def test_position_is_assigned_incrementally(auth_client, table):
    keys = []
    for name in ["A", "B", "C"]:
        response = auth_client.post(
            col_list(table.id), {"name": name, "type": "text"}, format="json"
        )
        keys.append(response.data["position"])

    assert keys == [0, 1, 2]


# ---------------------------------------------------------------- RF06 vencimento


def test_a_second_due_date_column_is_rejected(auth_client, table):
    auth_client.post(
        col_list(table.id), {"name": "Vence em", "type": "due_date"}, format="json"
    )
    response = auth_client.post(
        col_list(table.id), {"name": "Outro vencimento", "type": "due_date"}, format="json"
    )

    assert response.status_code == 400
    assert "type" in response.data


def test_the_single_due_date_rule_is_enforced_by_the_database(table):
    """
    A garantia real é o índice único parcial, não o serializer.

    Este teste passa por cima da API para provar que o Postgres também recusa.
    """
    Column.objects.create(table=table, name="Vence em", type=ColumnType.DUE_DATE, position=0)

    with pytest.raises(IntegrityError), transaction.atomic():
        Column.objects.create(
            table=table, name="Outro", type=ColumnType.DUE_DATE, position=1
        )


# ---------------------------------------------------------------- select/options


def test_select_without_options_is_rejected(auth_client, table):
    response = auth_client.post(
        col_list(table.id), {"name": "Status", "type": "select"}, format="json"
    )

    assert response.status_code == 400
    assert "options" in response.data


def test_non_select_with_options_is_rejected(auth_client, table):
    response = auth_client.post(
        col_list(table.id),
        {"name": "Cliente", "type": "text", "options": ["a", "b"]},
        format="json",
    )

    assert response.status_code == 400
    assert "options" in response.data


def test_select_rejects_duplicate_options(auth_client, table):
    response = auth_client.post(
        col_list(table.id),
        {"name": "Status", "type": "select", "options": ["Ativo", "Ativo"]},
        format="json",
    )

    assert response.status_code == 400


def test_select_with_options_is_accepted(auth_client, table):
    response = auth_client.post(
        col_list(table.id),
        {"name": "Status", "type": "select", "options": [" Ativo ", "Encerrado"]},
        format="json",
    )

    assert response.status_code == 201
    assert response.data["options"] == ["Ativo", "Encerrado"]  # espaços aparados


# ---------------------------------------------------------------- imutabilidade


def test_renaming_a_column_keeps_the_key(auth_client, table, columns):
    column = columns[0]

    response = auth_client.patch(
        col_detail(table.id, column.id), {"name": "Nome do cliente"}, format="json"
    )

    assert response.status_code == 200
    assert response.data["name"] == "Nome do cliente"
    # A chave é o que liga a coluna aos registros — renomear não pode reescrevê-la.
    assert response.data["key"] == "cliente"


def test_key_sent_in_the_payload_is_ignored(auth_client, table, columns):
    column = columns[0]

    auth_client.patch(
        col_detail(table.id, column.id), {"key": "chave_forjada"}, format="json"
    )

    column.refresh_from_db()
    assert column.key == "cliente"


def test_changing_the_type_is_rejected(auth_client, table, columns):
    column = columns[0]

    response = auth_client.patch(
        col_detail(table.id, column.id), {"type": "number"}, format="json"
    )

    assert response.status_code == 400
    assert "type" in response.data


def test_position_cannot_be_changed_by_patch(auth_client, table, columns):
    column = columns[0]

    auth_client.patch(col_detail(table.id, column.id), {"position": 4}, format="json")

    column.refresh_from_db()
    assert column.position == 0


# ---------------------------------------------------------------- reorder


def test_reorder_permutes_the_positions(auth_client, table, columns):
    reversed_ids = [str(c.id) for c in reversed(columns)]

    response = auth_client.patch(
        reorder_url(table.id), {"order": reversed_ids}, format="json"
    )

    assert response.status_code == 200
    assert [c["id"] for c in response.data] == reversed_ids
    assert list(
        Column.objects.filter(table=table).order_by("position").values_list("id", flat=True)
    ) == [c.id for c in reversed(columns)]


def test_reorder_swap_survives_the_intermediate_duplicate_position(
    auth_client, table, columns
):
    """
    Trocar duas colunas de lugar passa por um estado com posição duplicada.

    Só não estoura porque columns_unique_position é DEFERRABLE INITIALLY
    DEFERRED — a checagem acontece no COMMIT, não a cada UPDATE.
    """
    ids = [str(c.id) for c in columns]
    ids[0], ids[1] = ids[1], ids[0]

    response = auth_client.patch(reorder_url(table.id), {"order": ids}, format="json")

    assert response.status_code == 200
    assert [c["id"] for c in response.data] == ids


def test_reorder_rejects_an_incomplete_list(auth_client, table, columns):
    response = auth_client.patch(
        reorder_url(table.id), {"order": [str(columns[0].id)]}, format="json"
    )

    assert response.status_code == 400


def test_reorder_rejects_a_column_from_another_table(auth_client, table, columns, other_table):
    foreign = Column.objects.create(
        table=other_table, name="Intrusa", type=ColumnType.TEXT, position=0
    )
    ids = [str(c.id) for c in columns] + [str(foreign.id)]

    response = auth_client.patch(reorder_url(table.id), {"order": ids}, format="json")

    assert response.status_code == 400


# ---------------------------------------------------------------- RS01 / RS04


def test_cannot_list_columns_of_another_users_table(auth_client, other_table):
    assert auth_client.get(col_list(other_table.id)).status_code == 404


def test_cannot_create_a_column_in_another_users_table(auth_client, other_table):
    response = auth_client.post(
        col_list(other_table.id), {"name": "Invasora", "type": "text"}, format="json"
    )

    assert response.status_code == 404
    assert not Column.objects.filter(table=other_table).exists()


def test_cannot_delete_a_column_of_another_users_table(auth_client, other_table):
    foreign = Column.objects.create(
        table=other_table, name="Alvo", type=ColumnType.TEXT, position=0
    )

    assert auth_client.delete(col_detail(other_table.id, foreign.id)).status_code == 404
    assert Column.objects.filter(id=foreign.id).exists()


def test_cannot_reach_a_column_through_a_table_you_own(auth_client, table, other_table):
    """Id de coluna alheia sob a SUA tabela também não passa."""
    foreign = Column.objects.create(
        table=other_table, name="Alvo", type=ColumnType.TEXT, position=0
    )

    assert auth_client.get(col_detail(table.id, foreign.id)).status_code == 404


def test_columns_require_authentication(api_client, table):
    assert api_client.get(col_list(table.id)).status_code == 401


# ---------------------------------------------------------------- exclusão


def test_deleting_a_column_works(auth_client, table, columns):
    target = columns[0]

    assert auth_client.delete(col_detail(table.id, target.id)).status_code == 204
    assert not Column.objects.filter(id=target.id).exists()
