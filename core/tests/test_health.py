"""
Health check — liveness e readiness.

A separação não é de rigor, é de CONSEQUÊNCIA: `/api/health/` é o que a
plataforma consulta, e um health que a plataforma consulta é gatilho de
restart. `/api/health/ready/` é para quem observa, e por isso pode ser mais
exigente sem transformar degradação em indisponibilidade.
"""

from unittest.mock import patch

import pytest
from django.urls import reverse

# A URL do Redis carrega host, porta e — em produção — senha. Se um dia a
# exceção do cache vazar para o corpo da resposta, é esta string que aparece.
ERRO_COM_SEGREDO = "Error 111 connecting to redis://:senha-do-redis@redis:6379/1"


@pytest.mark.django_db
def test_health_is_public_and_reports_database(client):
    response = client.get(reverse("core:health"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "up"}


@pytest.mark.django_db
def test_ready_reports_every_dependency(client):
    response = client.get(reverse("core:ready"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "up", "redis": "up"}


@pytest.mark.django_db
def test_ready_devolve_503_com_o_redis_fora(client):
    with patch("core.views.cache.get", side_effect=Exception(ERRO_COM_SEGREDO)):
        response = client.get(reverse("core:ready"))

    assert response.status_code == 503
    assert response.json() == {"status": "unhealthy", "database": "up", "redis": "down"}


@pytest.mark.django_db
def test_ready_nao_vaza_o_erro_do_cache(client):
    """RS05 — o endpoint é AllowAny; a exceção do Redis carrega a URL inteira."""
    with patch("core.views.cache.get", side_effect=Exception(ERRO_COM_SEGREDO)):
        response = client.get(reverse("core:ready"))

    corpo = response.content.decode()
    for vazamento in ("senha-do-redis", "6379", "Error 111"):
        assert vazamento not in corpo


@pytest.mark.django_db
def test_liveness_nao_depende_do_redis(client):
    """
    O ponto da separação, em forma de teste.

    Com o Redis fora, a liveness precisa continuar 200 — senão a plataforma
    derruba e recria os containers de `web` em laço por causa de uma dependência
    que reiniciar não conserta, e uma queda de cache (que `core/throttling.py`
    absorve, falhando aberto) vira queda da aplicação.
    """
    with patch("core.views.cache.get", side_effect=Exception(ERRO_COM_SEGREDO)):
        response = client.get(reverse("core:health"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "up"}
