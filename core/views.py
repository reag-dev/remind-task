import logging

from django.core.cache import cache
from django.db import DatabaseError, connection
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

logger = logging.getLogger(__name__)

# Chave de sondagem do cache. O valor não importa e a leitura pode voltar vazia:
# o que se está perguntando é se o Redis RESPONDE, não o que ele guarda.
CHAVE_SONDA = "healthcheck:redis"


def _banco_responde() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        # RS05 — a mensagem do psycopg carrega host, porta e usuário do banco, e
        # estes endpoints são `AllowAny`: qualquer um lia a topologia interna só
        # pedindo o health durante uma indisponibilidade. O detalhe vai para o
        # log, onde o RedactingFilter já atua e onde quem opera o sistema o lê.
        logger.exception("Health check falhou ao alcançar o banco.")
        return False
    return True


def _cache_responde() -> bool:
    """
    Sonda o Redis pelo backend de CACHE, e não pelo broker do Celery.

    É o mesmo servidor (bancos 0 e 1 da mesma instância), mas o cache é o que o
    caminho de request realmente toca: é dele que os contadores de throttle
    saem. Sondar o broker exigiria abrir uma conexão do Celery dentro de uma
    view HTTP — mais peça no caminho de um endpoint que precisa ser barato.

    `Exception` e não uma família de erros específica, pelo mesmo motivo escrito
    em `core/throttling.py`: cada backend levanta a sua (`ConnectionError`,
    `TimeoutError`, erros de serialização…), e enumerá-las aqui garantiria
    descobrir a que faltou em produção, dentro do endpoint que existe para dizer
    que está tudo bem.
    """
    try:
        cache.get(CHAVE_SONDA)
    except Exception:
        logger.exception("Health check falhou ao alcançar o cache.")
        return False
    return True


@extend_schema(
    summary="Liveness",
    description=(
        "200 se o processo está de pé e alcança o banco; 503 caso contrário. "
        "É este que a plataforma consulta — de propósito **não** olha o Redis."
    ),
    responses={200: OpenApiTypes.OBJECT, 503: OpenApiTypes.OBJECT},
)
@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([])
def health(request):
    """
    Liveness: o processo serve requisição e alcança o banco.

    O contrato desta resposta não muda desde a Phase 3 porque é o que a
    plataforma consulta (`healthcheck: "/api/health/"` em `.railway/railway.ts`)
    e o que o `docker-compose` usa. Um 200 que não toca o banco não prova nada —
    o processo pode estar de pé servindo 500 em toda rota real.

    **Por que o Redis não entra aqui.** Um health que a plataforma consulta é um
    gatilho de RESTART: falhou, o container é derrubado e sobe outro. Com o
    Redis na conta, uma queda do cache — que hoje degrada throttle e alertas, e
    nada mais, porque `core/throttling.py` falha aberto — passaria a reiniciar
    todos os containers de `web` em laço, sem que reiniciar conserte coisa
    alguma do lado do Redis. Seria transformar degradação em indisponibilidade,
    que é exatamente o que a Phase 4 recusou fazer. Quem quer o quadro completo
    consulta `/api/health/ready/`.
    """
    if not _banco_responde():
        return Response(
            {"status": "unhealthy", "database": "down"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response({"status": "ok", "database": "up"})


@extend_schema(
    summary="Readiness",
    description=(
        "Estado das dependências — banco e Redis. 503 se qualquer uma estiver "
        "fora. Endpoint de observação: a plataforma **não** o consulta."
    ),
    responses={200: OpenApiTypes.OBJECT, 503: OpenApiTypes.OBJECT},
)
@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([])
def ready(request):
    """
    Readiness: o quadro completo das dependências, para quem observa.

    A diferença para o `health` não é de rigor, é de CONSEQUÊNCIA: este aqui
    ninguém usa como gatilho de restart. Ele existe para que a queda do Redis
    seja vista por quem opera o sistema antes de virar "os alertas pararam de
    chegar" na boca do usuário — que é o objetivo desta phase.
    """
    dependencias = {
        "database": "up" if _banco_responde() else "down",
        "redis": "up" if _cache_responde() else "down",
    }
    tudo_de_pe = all(estado == "up" for estado in dependencias.values())

    # Sem `str(exc)` na resposta, pelo mesmo motivo do `health`: o endpoint é
    # público, e a URL do Redis carrega host, porta e — em produção — senha.
    return Response(
        {"status": "ok" if tudo_de_pe else "unhealthy", **dependencias},
        status=status.HTTP_200_OK if tudo_de_pe else status.HTTP_503_SERVICE_UNAVAILABLE,
    )
