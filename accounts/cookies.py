"""
Transporte do refresh token via cookie httpOnly (RS07).

Por que não devolver o refresh no corpo da resposta: o cliente teria que guardá-lo
em `localStorage` ou `sessionStorage`, ambos legíveis por qualquer JavaScript da
página. Um único XSS entregaria um token de 7 dias. Em cookie `httpOnly` o
navegador envia sozinho e o JS não enxerga.

O access token continua no corpo — vida curta (15 min) e mantido em memória pelo
cliente, nunca persistido.
"""

from django.conf import settings
from rest_framework.response import Response


def set_refresh_cookie(response: Response, token: str) -> Response:
    response.set_cookie(
        key=settings.AUTH_COOKIE_NAME,
        value=token,
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        httponly=settings.AUTH_COOKIE_HTTPONLY,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        # Restringe o envio aos endpoints de auth: nenhuma rota de dados recebe
        # o refresh, então ele não aparece em log de request de /api/tables/ etc.
        path=settings.AUTH_COOKIE_PATH,
    )
    return response


def delete_refresh_cookie(response: Response) -> Response:
    response.delete_cookie(
        key=settings.AUTH_COOKIE_NAME,
        path=settings.AUTH_COOKIE_PATH,
        samesite=settings.AUTH_COOKIE_SAMESITE,
    )
    return response


def read_refresh_token(request) -> str | None:
    """Corpo tem precedência sobre cookie — útil para clientes não-browser."""
    return request.data.get("refresh") or request.COOKIES.get(settings.AUTH_COOKIE_NAME)
