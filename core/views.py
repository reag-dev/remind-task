import logging

from django.db import DatabaseError, connection
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

logger = logging.getLogger(__name__)


@extend_schema(
    summary="Health check",
    description="Retorna 200 se a aplicação alcança o banco; 503 caso contrário.",
    responses={
        200: OpenApiTypes.OBJECT,
        503: OpenApiTypes.OBJECT,
    },
)
@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    """Health check com dependência real — um 200 que não toca o banco não prova nada."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        # RS05 — a mensagem do psycopg carrega host, porta e usuário do banco, e
        # este endpoint é `AllowAny`: qualquer um lia a topologia interna só
        # pedindo o health durante uma indisponibilidade. O detalhe vai para o
        # log, onde o RedactingFilter já atua e onde quem opera o sistema o lê.
        logger.exception("Health check falhou ao alcançar o banco.")
        return Response(
            {"status": "unhealthy", "database": "down"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response({"status": "ok", "database": "up"})
