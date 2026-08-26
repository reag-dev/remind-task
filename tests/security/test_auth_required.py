"""
Critério 4 da seção 10 — "endpoints protegidos exigem autenticação".

Dois testes, com papéis diferentes:

1. `test_every_api_route_is_classified` varre a URLconf e falha se aparecer uma
   rota que ninguém classificou. É a parte que **cresce com o app**: quem
   adicionar um endpoint amanhã tem de dizer aqui se ele é público ou protegido,
   e essa decisão vira revisão de código em vez de descuido.
2. O teste parametrizado prova o 401 em cada rota protegida.

Sem o primeiro, o segundo viraria uma lista congelada: um endpoint novo e sem
permissão passaria despercebido justamente porque não estaria na lista.
"""

import pytest
from django.urls import get_resolver, reverse
from django.urls.resolvers import URLResolver

pytestmark = pytest.mark.django_db

# Rotas abertas de propósito, com o motivo de cada uma.
PUBLICAS = {
    "core:health": "sonda de liveness do compose e do orquestrador",
    "core:ready": "sonda de readiness — mesma razão, e cobre banco e Redis",
    "accounts:register": "criar conta é o que antecede ter token",
    "accounts:login": "idem",
    "accounts:refresh": "a autoridade é o refresh token no cookie, não o access",
    "accounts:logout": "encerrar sessão precisa funcionar com o access já expirado",
    "accounts:password-reset": "quem esqueceu a senha não tem como se autenticar",
    "accounts:password-reset-confirm": "idem — a autoridade é o token do e-mail",
    "schema": "descreve a forma da API, nunca dado — drf-spectacular serve com AllowAny",
    "swagger-ui": "idem",
}

# Rotas protegidas → como montar uma URL válida a partir dos recursos do dono.
# A URL não precisa apontar para nada existente: sem token, a resposta tem de ser
# 401 ANTES de qualquer consulta ao banco.
PROTEGIDAS = {
    "accounts:me": lambda r: reverse("accounts:me"),
    "tables:api-root": lambda r: reverse("tables:api-root"),
    "tables:table-list": lambda r: reverse("tables:table-list"),
    "tables:table-detail": lambda r: reverse("tables:table-detail", args=[r.table.id]),
    "tables:column-list": lambda r: reverse("tables:column-list", args=[r.table.id]),
    "tables:column-detail": lambda r: reverse(
        "tables:column-detail", args=[r.table.id, r.column.id]
    ),
    "tables:column-reorder": lambda r: reverse(
        "tables:column-reorder", args=[r.table.id]
    ),
    "records:api-root": lambda r: reverse("records:api-root", args=[r.table.id]),
    "records:record-list": lambda r: reverse("records:record-list", args=[r.table.id]),
    "records:record-detail": lambda r: reverse(
        "records:record-detail", args=[r.table.id, r.record.id]
    ),
    "records:record-export": lambda r: reverse(
        "records:record-export", args=[r.table.id]
    ),
    "alerts:api-root": lambda r: reverse("alerts:api-root"),
    "alerts:alert-list": lambda r: reverse("alerts:alert-list"),
    "alerts:alert-detail": lambda r: reverse("alerts:alert-detail", args=[r.alert.id]),
    "alerts:alert-read": lambda r: reverse("alerts:alert-read", args=[r.alert.id]),
    "alerts:alert-dismiss": lambda r: reverse(
        "alerts:alert-dismiss", args=[r.alert.id]
    ),
    "alerts:alert-rule-list": lambda r: reverse(
        "alerts:alert-rule-list", args=[r.table.id]
    ),
    "alerts:alert-rule-detail": lambda r: reverse(
        "alerts:alert-rule-detail", args=[r.table.id, r.rule.id]
    ),
}


def _walk(resolver, prefix="", namespaces=()):
    for pattern in resolver.url_patterns:
        if isinstance(pattern, URLResolver):
            child = namespaces + ((pattern.namespace,) if pattern.namespace else ())
            yield from _walk(pattern, prefix + str(pattern.pattern), child)
        elif pattern.name:
            yield prefix + str(pattern.pattern), ":".join((*namespaces, pattern.name))


def rotas_da_api() -> set[str]:
    """
    Nomes de rota sob `/api/`.

    As variantes de sufixo de formato (`.json`) do DRF são descartadas: mesma
    view, mesmo nome, e a URL sem sufixo já as representa.
    """
    return {
        nome
        for caminho, nome in _walk(get_resolver())
        if caminho.startswith("api/") and "format" not in caminho
    }


def test_every_api_route_is_classified():
    """
    Tripwire. Endpoint novo entra aqui antes de entrar em produção.

    Falhar com "não classificada" é o ponto: obriga quem adicionou a rota a
    declarar se ela é pública, e a decisão passa a aparecer no diff.
    """
    classificadas = set(PUBLICAS) | set(PROTEGIDAS)
    encontradas = rotas_da_api()

    assert not (encontradas - classificadas), (
        f"rota(s) não classificada(s): {sorted(encontradas - classificadas)}"
    )
    assert not (classificadas - encontradas), (
        f"rota(s) classificada(s) que não existem mais: {sorted(classificadas - encontradas)}"
    )


@pytest.mark.parametrize("nome", sorted(PROTEGIDAS))
def test_protected_routes_reject_anonymous_requests(api_client, mine, nome):
    url = PROTEGIDAS[nome](mine)

    for metodo in ("get", "post", "put", "patch", "delete"):
        response = getattr(api_client, metodo)(url, {}, format="json")
        assert response.status_code in (401, 405), (
            f"{metodo.upper()} {nome} respondeu {response.status_code} sem token"
        )


@pytest.mark.parametrize("nome", sorted(PROTEGIDAS))
def test_protected_routes_reject_a_garbage_token(api_client, mine, nome):
    """
    401 também para token inventado.

    Sem isto, uma view que trocasse `IsAuthenticated` por uma checagem própria
    do header (`if request.headers.get("Authorization")`) passaria no teste
    anônimo e continuaria aberta para qualquer string.
    """
    api_client.credentials(HTTP_AUTHORIZATION="Bearer nao.e.um.token")

    response = api_client.get(PROTEGIDAS[nome](mine))

    assert response.status_code in (401, 405)


def test_public_routes_answer_without_a_token(api_client):
    """A contraprova: as rotas abertas continuam abertas."""
    assert api_client.get(reverse("core:health")).status_code == 200
    assert api_client.get(reverse("core:ready")).status_code == 200
    assert api_client.get(reverse("schema")).status_code == 200
