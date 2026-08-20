"""
Critérios 1, 2, 3 e 9 da seção 10 — e o ataque descrito em RS04.

    GET /api/tables/<id de outro dono>/

Autenticado como A, todo recurso de B tem de responder **404**. Nunca 200, e
nunca 403: um 403 confirmaria que o recurso existe, que é exatamente a informação
que quem sonda ids está atrás.
"""

import pytest
from django.urls import reverse

from alerts.models import Alert, AlertRule
from records.models import Record
from tables.models import Column, Table

pytestmark = pytest.mark.django_db

# Um alvo por tipo de recurso endereçável por id. As lambdas recebem os recursos
# de B; o client é sempre o de A.
LEGIVEIS = {
    "tabela": lambda r: reverse("tables:table-detail", args=[r.table.id]),
    "colunas": lambda r: reverse("tables:column-list", args=[r.table.id]),
    "coluna": lambda r: reverse("tables:column-detail", args=[r.table.id, r.column.id]),
    "registros": lambda r: reverse("records:record-list", args=[r.table.id]),
    "registro": lambda r: reverse("records:record-detail", args=[r.table.id, r.record.id]),
    "export": lambda r: reverse("records:record-export", args=[r.table.id]),
    "regras-de-alerta": lambda r: reverse("alerts:alert-rule-list", args=[r.table.id]),
    "regra-de-alerta": lambda r: reverse(
        "alerts:alert-rule-detail", args=[r.table.id, r.rule.id]
    ),
    "alerta": lambda r: reverse("alerts:alert-detail", args=[r.alert.id]),
}

# Rotas que só existem para escrever: GET nelas é 405 por construção, antes de
# qualquer objeto ser resolvido. Ficam fora do teste de leitura e dentro de todos
# os outros.
ACOES = {
    "reorder-de-colunas": lambda r: reverse("tables:column-reorder", args=[r.table.id]),
    "alerta-lido": lambda r: reverse("alerts:alert-read", args=[r.alert.id]),
    "alerta-descartado": lambda r: reverse("alerts:alert-dismiss", args=[r.alert.id]),
}

TARGETS = {**LEGIVEIS, **ACOES}

WRITE_METHODS = ("post", "put", "patch", "delete")


@pytest.mark.parametrize("alvo", sorted(LEGIVEIS))
def test_reading_a_foreign_resource_returns_404(auth_client, theirs, alvo):
    """Critérios 1 e 9."""
    response = auth_client.get(LEGIVEIS[alvo](theirs))

    assert response.status_code == 404, f"{alvo} vazou com {response.status_code}"


@pytest.mark.parametrize("alvo", sorted(TARGETS))
@pytest.mark.parametrize("metodo", WRITE_METHODS)
def test_writing_to_a_foreign_resource_never_succeeds(auth_client, theirs, alvo, metodo):
    """
    Critérios 2 e 3.

    405 é resposta aceitável — o método não existe naquela rota, e nada vazou.
    O que não pode acontecer é 2xx (a escrita passou) nem 3xx (foi para algum
    lugar). O 403 tem teste próprio logo abaixo.
    """
    response = getattr(auth_client, metodo)(
        TARGETS[alvo](theirs), {"name": "Invadida"}, format="json"
    )

    assert response.status_code in (404, 405), (
        f"{metodo.upper()} em {alvo} respondeu {response.status_code}"
    )


@pytest.mark.parametrize("alvo", sorted(TARGETS))
def test_a_foreign_resource_is_never_answered_with_403(auth_client, theirs, alvo):
    """
    Critério 9 — RS04.

    403 significa "existe, mas você não pode". Para quem está varrendo ids, é a
    confirmação que ele procura. A resposta correta é 404: indistinguível de um
    id que nunca existiu.
    """
    url = TARGETS[alvo](theirs)

    for metodo in ("get", *WRITE_METHODS):
        response = getattr(auth_client, metodo)(url, {}, format="json")
        assert response.status_code != 403, f"{metodo.upper()} em {alvo} devolveu 403"


def test_no_foreign_resource_was_touched(auth_client, theirs):
    """
    A tentativa não pode ter efeito colateral.

    Um 404 devolvido DEPOIS de a escrita acontecer seria pior do que um 200
    honesto: o dono não saberia que o dado mudou.
    """
    for build in TARGETS.values():
        url = build(theirs)
        for metodo in WRITE_METHODS:
            getattr(auth_client, metodo)(url, {"name": "Invadida"}, format="json")

    assert Table.objects.filter(id=theirs.table.id, name="Contratos de B").exists()
    assert Column.objects.filter(id=theirs.column.id).exists()
    assert Record.objects.filter(id=theirs.record.id).exists()
    assert AlertRule.objects.filter(id=theirs.rule.id).exists()
    assert Alert.objects.filter(id=theirs.alert.id, status=theirs.alert.status).exists()


def test_listing_never_mixes_owners(auth_client, mine, theirs):
    """
    O outro lado do mesmo requisito: as coleções sem id também não podem vazar.

    O teste por id não pegaria uma listagem que esquecesse o filtro — ela
    responderia 200 com tudo dentro.
    """
    tabelas = auth_client.get(reverse("tables:table-list")).data["results"]
    assert [t["id"] for t in tabelas] == [str(mine.table.id)]

    registros = auth_client.get(
        reverse("records:record-list", args=[mine.table.id])
    ).data["results"]
    assert [r["id"] for r in registros] == [str(mine.record.id)]

    alertas = auth_client.get(reverse("alerts:alert-list")).data["results"]
    assert [a["id"] for a in alertas] == [str(mine.alert.id)]
