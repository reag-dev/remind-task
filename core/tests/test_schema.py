"""
`/api/docs/` é a "UI" do MVP — o plano descartou SPA de propósito.

Isso muda o peso do schema: ele não é documentação auxiliar, é a interface pela
qual alguém exercita o sistema. Um endpoint que sai do schema fica invisível, e
uma anotação quebrada derruba a página inteira.
"""

import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.urls import reverse

pytestmark = pytest.mark.django_db

# As `@action` são as que somem calado: um decorator sem `extend_schema` ou uma
# assinatura que o spectacular não consegue inferir, e a rota desaparece da
# página sem quebrar teste nenhum.
ACOES_CUSTOMIZADAS = (
    "/api/tables/{table_id}/records/export/",
    "/api/tables/{table_id}/columns/reorder/",
    "/api/alerts/{id}/read/",
    "/api/alerts/{id}/dismiss/",
)


@pytest.fixture(scope="module")
def schema():
    saida = StringIO()
    # `--fail-on-warn` é o que dá dente: sem ele o comando sai com 0 mesmo
    # listando "could not resolve serializer" e publicando um schema furado.
    call_command("spectacular", format="openapi-json", stdout=saida, fail_on_warn=True)
    return json.loads(saida.getvalue())


def test_the_schema_builds_without_warnings(schema):
    assert schema["openapi"].startswith("3.")


@pytest.mark.parametrize("caminho", ACOES_CUSTOMIZADAS)
def test_every_custom_action_is_documented(schema, caminho):
    assert caminho in schema["paths"], f"{caminho} sumiu da documentação"


def test_the_schema_says_how_to_authenticate(schema):
    """
    Sem `securitySchemes` o Swagger perde o botão "Authorize" e vira uma lista
    de endpoints que ninguém consegue chamar.
    """
    esquemas = schema["components"]["securitySchemes"]

    assert esquemas["jwtAuth"]["scheme"] == "bearer"
    assert "cookieAuth" in esquemas


def test_the_whole_api_surface_is_documented(schema):
    """
    Contraprova de cobertura: toda rota classificada como pública ou protegida
    na suíte de segurança tem de aparecer aqui.

    Reusa a classificação de `tests/security/test_auth_required.py` de propósito
    — é a mesma lista que já é obrigada a crescer com o app.
    """
    from tests.security.test_auth_required import PROTEGIDAS, PUBLICAS

    # O router root do DRF e as próprias páginas de schema não entram no
    # documento — o spectacular as ignora por construção.
    fora_do_schema = {"schema", "swagger-ui"}
    esperadas = {
        nome
        for nome in set(PROTEGIDAS) | set(PUBLICAS)
        if not nome.endswith("api-root") and nome not in fora_do_schema
    }

    # Igualdade, não ">=": aqui a correspondência é 1 para 1 — cada nome de rota
    # classificado vira exatamente um caminho no documento. Uma desigualdade
    # deixaria passar tanto endpoint sem documentação quanto caminho fantasma.
    assert len(schema["paths"]) == len(esperadas), (
        f"{len(esperadas)} rotas classificadas, {len(schema['paths'])} caminhos no schema"
    )


def test_the_docs_page_is_served(client):
    assert client.get(reverse("swagger-ui")).status_code == 200
    assert client.get(reverse("schema")).status_code == 200
