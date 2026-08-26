"""
Ajustes de OpenAPI (drf-spectacular): esquemas de autenticação e um AutoSchema.

As classes de autenticação do projeto são subclasses (`core.rls.RLSJWTAuthentication`),
e o drf-spectacular casa extensões por classe EXATA, não por herança. Sem estas
duas declarações ele emite W001 e publica o schema sem `securitySchemes` — o
Swagger de `/api/docs/` perderia o botão de "Authorize" e ninguém conseguiria
exercitar a API pela documentação.

O `AutoSchemaComCorpoNoDelete`, no fim do arquivo, resolve um problema irmão: um
corpo que existe na API e não existe no documento.
"""

from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.openapi import AutoSchema


class RLSJWTScheme(OpenApiAuthenticationExtension):
    target_class = "core.rls.RLSJWTAuthentication"
    name = "jwtAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}


class RLSSessionScheme(OpenApiAuthenticationExtension):
    target_class = "core.rls.RLSSessionAuthentication"
    name = "cookieAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "apiKey", "in": "cookie", "name": "sessionid"}


class AutoSchemaComCorpoNoDelete(AutoSchema):
    """
    Faz um `DELETE` com corpo aparecer no documento.

    O drf-spectacular descarta o corpo de qualquer método fora de PUT/PATCH/POST
    — a checagem é a primeira linha de `AutoSchema._get_request_body()`, e ela
    ignora um `extend_schema(request=...)` calado, sem W001 que o `fail_on_warn`
    de `core/tests/test_schema.py` pudesse pegar. Para quase toda API é o
    comportamento certo: o RFC 9110 diz que corpo em DELETE não tem semântica
    definida, então omitir é um bom padrão.

    `DELETE /api/auth/me/` é a exceção deliberada (ver `AccountDeleteSerializer`),
    e aqui o preço da omissão não é cosmético, pelo mesmo motivo das duas classes
    acima: `/api/docs/` é a interface pela qual se exercita esta API. Um endpoint
    documentado como "exige a senha atual no corpo", mas sem corpo no schema,
    responde 400 a todo mundo que apertar "Try it out" — sem campo para
    preencher e sem pista do que falta.

    O escopo é o menor possível: só o método DELETE muda, só quando a view
    declarou um `request`, e só nas views que pedem esta classe explicitamente —
    não é `DEFAULT_SCHEMA_CLASS`.
    """

    def _get_request_body(self, direction="request"):
        if self.method != "DELETE":
            return super()._get_request_body(direction)

        # A recusa do pai é uma comparação com `self.method`, e não há gancho
        # antes dela. Emprestar "POST" pela duração da chamada é o menor desvio
        # disponível: a montagem do corpo em si não volta a olhar para o método
        # (o caminho que olha é o `partial` do PATCH, que não passa por aqui).
        # `finally` porque o mesmo objeto monta as outras operações da view logo
        # depois — deixar "POST" para trás renomearia a operação.
        self.method = "POST"
        try:
            return super()._get_request_body(direction)
        finally:
            self.method = "DELETE"
