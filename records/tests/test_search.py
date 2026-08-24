"""
Busca textual nos registros (`?q=`).

O eixo que exige mais cuidado aqui não é achar — é **não** achar: colunas
marcadas como `is_sensitive` não podem ser varridas. Ver
`test_sensitive_column_is_not_searchable`.
"""

import pytest
from django.urls import reverse

from records.models import Record
from tables.models import Column, ColumnType, Table

pytestmark = pytest.mark.django_db


def rec_list(table_id):
    return reverse("records:record-list", args=[table_id])


@pytest.fixture
def cenario(db, user):
    """
    Uma tabela com uma coluna de cada tipo que importa para a busca.

    `responsavel` é sensível e `categoria` é `select` — as duas ficam de fora da
    varredura, por motivos diferentes.
    """
    table = Table.objects.create(user=user, name="Contratos")
    specs = [
        ("Cliente", ColumnType.TEXT, {}),
        ("Contato", ColumnType.EMAIL, {}),
        ("Responsável", ColumnType.TEXT, {"is_sensitive": True}),
        ("Categoria", ColumnType.SELECT, {"options": ["Ouro", "Prata"]}),
        ("Valor", ColumnType.NUMBER, {}),
        ("Vence", ColumnType.DUE_DATE, {}),
    ]
    for i, (name, type_, extra) in enumerate(specs):
        Column.objects.create(table=table, name=name, type=type_, position=i, **extra)

    linhas = [
        {
            "cliente": "Padaria Aurora",
            "contato": "compras@aurora.com.br",
            "responsavel": "Marina Toledo",
            "categoria": "Ouro",
            "valor": 1500,
            "vence": "2026-01-10",
        },
        {
            "cliente": "Mercado Boreal",
            "contato": "financeiro@boreal.com",
            "responsavel": "Ana Prado",
            "categoria": "Prata",
            "valor": 2500,
            "vence": "2026-06-20",
        },
        {
            "cliente": "Oficina Central",
            "contato": "contato@central.net",
            "responsavel": "Marina Toledo",
            "categoria": "Ouro",
            "valor": 1500,
            "vence": "2026-12-31",
        },
    ]
    for linha in linhas:
        Record.objects.create(table=table, data=linha)
    return table


def buscar(authenticate, user, table, termo):
    resposta = authenticate(user).get(rec_list(table.id), {"q": termo})
    assert resposta.status_code == 200, resposta.data
    return [linha["data"]["cliente"] for linha in resposta.data["results"]]


# ------------------------------------------------------------------ achar


def test_finds_by_substring_of_a_text_column(authenticate, user, cenario):
    assert buscar(authenticate, user, cenario, "aurora") == ["Padaria Aurora"]


def test_search_is_case_insensitive(authenticate, user, cenario):
    assert buscar(authenticate, user, cenario, "BOREAL") == ["Mercado Boreal"]


def test_matches_in_the_middle_of_the_value(authenticate, user, cenario):
    """
    O valor vive dentro de um JSONB, e o Django compara com `->>`, não com
    `->`. Se fosse `->` a comparação enxergaria as aspas do JSON e uma busca
    ancorada se comportaria de forma diferente da de uma coluna comum.
    """
    assert buscar(authenticate, user, cenario, "ficina") == ["Oficina Central"]


def test_searches_email_columns_too(authenticate, user, cenario):
    """`email` é texto que alguém digitou — e é onde se procura um domínio."""
    assert buscar(authenticate, user, cenario, "boreal.com") == ["Mercado Boreal"]


def test_one_term_can_match_several_records(authenticate, user, cenario):
    assert sorted(buscar(authenticate, user, cenario, "a")) == [
        "Mercado Boreal",
        "Oficina Central",
        "Padaria Aurora",
    ]


def test_no_match_returns_an_empty_list_not_an_error(authenticate, user, cenario):
    assert buscar(authenticate, user, cenario, "inexistente-xyz") == []


# -------------------------------------------------------------- não achar


def test_sensitive_column_is_not_searchable(authenticate, user, cenario):
    """
    RS05 — o teste central deste arquivo.

    "Marina Toledo" está em `responsavel`, que é `is_sensitive` e aparece
    mascarada na UI. Se a busca a varresse, o valor sairia por tentativa e erro:
    quem procura `Mar`, depois `Mari`, e observa quando o registro some, leu o
    campo sem nunca vê-lo. O mascaramento viraria enfeite.
    """
    assert buscar(authenticate, user, cenario, "Marina") == []
    assert buscar(authenticate, user, cenario, "Toledo") == []


def test_select_column_is_not_searchable(authenticate, user, cenario):
    """
    `select` é domínio fechado: os valores possíveis são conhecidos e merecem
    filtro por igualdade. Varrê-lo com `ILIKE` faria `Ouro` casar por substring
    em qualquer lugar e confundiria busca com filtro.
    """
    assert buscar(authenticate, user, cenario, "Ouro") == []


def test_number_column_is_not_searchable(authenticate, user, cenario):
    """
    `1500` é o valor de dois registros. Buscar números como substring casaria
    `150` com `1500` e `15000` — e existe filtro próprio para faixa.
    """
    assert buscar(authenticate, user, cenario, "1500") == []


def test_table_without_searchable_columns_returns_nothing(authenticate, user):
    """
    `none()`, não o queryset intacto.

    Devolver tudo faria a busca parecer ter casado com a tabela inteira — o
    usuário leria a lista completa como "resultado". A lista vazia diz a
    verdade: não há onde procurar.
    """
    table = Table.objects.create(user=user, name="Só números")
    Column.objects.create(table=table, name="Valor", type=ColumnType.NUMBER, position=0)
    Record.objects.create(table=table, data={"valor": 10})

    assert buscar(authenticate, user, table, "10") == []


# ------------------------------------------------------------ composição


def test_blank_term_does_not_filter(authenticate, user, cenario):
    """`?q=` vazio é o estado inicial do campo na UI, não um filtro."""
    assert len(buscar(authenticate, user, cenario, "   ")) == 3


def test_search_combines_with_other_filters_as_and(authenticate, user, cenario):
    """
    Busca e filtro se somam em E.

    O teste só tem dente porque as duas pontas são medidas: `q=a` sozinho traz
    os três registros, e acrescentar `due_before` **reduz** para dois. Se a
    composição fosse OU, acrescentar filtro alargaria o resultado — o oposto do
    que a UI promete ao exibir busca e filtro ativos ao mesmo tempo.
    """
    assert len(buscar(authenticate, user, cenario, "a")) == 3

    resposta = authenticate(user).get(
        rec_list(cenario.id), {"q": "a", "due_before": "2026-07-01"}
    )

    assert resposta.status_code == 200
    assert sorted(linha["data"]["cliente"] for linha in resposta.data["results"]) == [
        "Mercado Boreal",
        "Padaria Aurora",
    ]


def test_search_does_not_cross_tables(authenticate, user, other_user, cenario):
    """
    RS01. A busca opera sobre o queryset já delimitado por tabela e dono, mas um
    filtro que montasse o próprio `Q` do zero poderia perder isso em silêncio.
    """
    outra = Table.objects.create(user=other_user, name="Alheia")
    Column.objects.create(table=outra, name="Cliente", type=ColumnType.TEXT, position=0)
    Record.objects.create(table=outra, data={"cliente": "Padaria Aurora"})

    assert buscar(authenticate, user, cenario, "Aurora") == ["Padaria Aurora"]
    assert len(buscar(authenticate, user, cenario, "Aurora")) == 1


def test_export_honours_the_search(authenticate, user, cenario):
    """
    RS08 — o export usa o mesmo `filter_queryset()` da listagem, então `?q=`
    vale lá sem código novo. O teste existe para que continue assim.
    """
    resposta = authenticate(user).get(
        reverse("records:record-export", args=[cenario.id]), {"q": "aurora"}
    )

    assert resposta.status_code == 200
    corpo = b"".join(resposta.streaming_content).decode("utf-8")
    assert "Padaria Aurora" in corpo
    assert "Mercado Boreal" not in corpo
