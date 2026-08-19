import pytest
from django.urls import reverse

from tables.models import Table

pytestmark = pytest.mark.django_db

LIST = reverse("tables:table-list")


def detail(table_id):
    return reverse("tables:table-detail", args=[table_id])


# ---------------------------------------------------------------- RF03 criação


def test_create_table_assigns_the_requesting_user(auth_client, user):
    response = auth_client.post(LIST, {"name": "Contratos"}, format="json")

    assert response.status_code == 201
    assert Table.objects.get(id=response.data["id"]).user == user


def test_create_table_ignores_user_sent_in_the_payload(auth_client, user, other_user):
    """O dono vem do token. Mandar `user` no corpo não muda nada."""
    response = auth_client.post(
        LIST, {"name": "Tentativa", "user": str(other_user.id)}, format="json"
    )

    assert response.status_code == 201
    assert Table.objects.get(id=response.data["id"]).user == user


def test_create_table_rejects_duplicate_name_for_the_same_user(auth_client, table):
    response = auth_client.post(LIST, {"name": table.name}, format="json")

    assert response.status_code == 400
    assert "name" in response.data


def test_two_users_can_have_tables_with_the_same_name(auth_client, other_table):
    response = auth_client.post(LIST, {"name": other_table.name}, format="json")

    assert response.status_code == 201


def test_create_table_rejects_out_of_range_lead_days(auth_client):
    response = auth_client.post(
        LIST, {"name": "Fora de faixa", "alert_lead_days": 400}, format="json"
    )

    assert response.status_code == 400
    assert "alert_lead_days" in response.data


def test_blank_name_is_rejected(auth_client):
    response = auth_client.post(LIST, {"name": "   "}, format="json")

    assert response.status_code == 400


# ---------------------------------------------------------------- RF04 leitura


def test_list_returns_only_own_tables(auth_client, table, other_table):
    response = auth_client.get(LIST)

    assert response.status_code == 200
    returned = {row["id"] for row in response.data["results"]}
    assert returned == {str(table.id)}


def test_retrieve_embeds_the_columns(auth_client, table, columns):
    response = auth_client.get(detail(table.id))

    assert response.status_code == 200
    assert [c["key"] for c in response.data["columns"]] == [
        "cliente", "contrato", "responsavel", "data_de_vencimento", "status"
    ]


# ---------------------------------------------------------------- RS01 / RS04


@pytest.mark.parametrize(
    "method,payload",
    [
        ("get", None),
        ("patch", {"name": "Sequestrada"}),
        ("put", {"name": "Sequestrada"}),
        ("delete", None),
    ],
)
def test_cannot_touch_another_users_table(auth_client, other_table, method, payload):
    """
    RS04: trocar o id na URL não dá acesso.

    A resposta é 404 e não 403 de propósito — 403 confirmaria que a tabela
    existe, entregando informação a quem está sondando ids.
    """
    call = getattr(auth_client, method)
    response = call(detail(other_table.id), payload, format="json") if payload else call(detail(other_table.id))

    assert response.status_code == 404
    assert Table.objects.filter(id=other_table.id).exists()


def test_deleting_own_table_works(auth_client, table):
    assert auth_client.delete(detail(table.id)).status_code == 204
    assert not Table.objects.filter(id=table.id).exists()


def test_deleting_a_table_removes_its_columns(auth_client, table, columns):
    from tables.models import Column

    auth_client.delete(detail(table.id))

    assert not Column.objects.filter(table_id=table.id).exists()


# ---------------------------------------------------------------- autenticação


@pytest.mark.parametrize("url", [LIST])
def test_requires_authentication(api_client, url):
    assert api_client.get(url).status_code == 401
