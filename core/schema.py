"""
Esquemas de autenticação para o OpenAPI (drf-spectacular).

As classes de autenticação do projeto são subclasses (`core.rls.RLSJWTAuthentication`),
e o drf-spectacular casa extensões por classe EXATA, não por herança. Sem estas
duas declarações ele emite W001 e publica o schema sem `securitySchemes` — o
Swagger de `/api/docs/` perderia o botão de "Authorize" e ninguém conseguiria
exercitar a API pela documentação.
"""

from drf_spectacular.extensions import OpenApiAuthenticationExtension


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
