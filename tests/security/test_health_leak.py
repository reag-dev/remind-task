"""
RS05 no endpoint mais exposto que existe.

`/api/health/` é `AllowAny` — não pede credencial nenhuma. Ele também é o
endpoint que a plataforma consulta de fora, então está sempre alcançável.

Antes desta phase, o 503 devolvia `str(exc)` do psycopg, que traz **host, porta
e usuário do banco**. Ou seja: bastava pedir o health durante uma
indisponibilidade para ler a topologia interna, sem autenticação. O projeto
aplica RS05 com rigor no log; a resposta HTTP tinha ficado de fora.
"""

import logging

import pytest
from django.db import DatabaseError
from django.urls import reverse

pytestmark = pytest.mark.django_db

# Imita o que o psycopg devolve quando não alcança o servidor: a mensagem real
# carrega os três dados de uma vez.
ERRO_DO_PSYCOPG = (
    'connection to server at "db-interno.railway.internal" (10.0.3.7), '
    'port 5432 failed: FATAL: password authentication failed for user "remind_app"'
)

SEGREDOS = ["db-interno.railway.internal", "10.0.3.7", "5432", "remind_app"]


@pytest.fixture
def banco_fora(monkeypatch):
    def explode(*args, **kwargs):
        raise DatabaseError(ERRO_DO_PSYCOPG)

    monkeypatch.setattr("core.views.connection.cursor", explode)


def test_health_ok_quando_o_banco_responde(api_client):
    resposta = api_client.get(reverse("core:health"))

    assert resposta.status_code == 200
    assert resposta.data == {"status": "ok", "database": "up"}


def test_503_nao_revela_host_porta_nem_usuario(api_client, banco_fora):
    resposta = api_client.get(reverse("core:health"))

    assert resposta.status_code == 503

    corpo = resposta.content.decode()
    for segredo in SEGREDOS:
        assert segredo not in corpo, f"o corpo do 503 vazou {segredo!r}"


def test_503_ainda_diz_o_que_a_plataforma_precisa_saber(api_client, banco_fora):
    """
    Redigir não pode virar silêncio: o health existe para a plataforma decidir
    tirar a instância do balanceador. O status precisa continuar legível.
    """
    resposta = api_client.get(reverse("core:health"))

    assert resposta.data == {"status": "unhealthy", "database": "down"}


def test_o_detalhe_vai_para_o_log_em_vez_de_sumir(api_client, banco_fora, caplog):
    """
    O outro lado da moeda. Quem opera o sistema precisa do erro real — o que
    muda é o canal: log (autenticado, redigido pelo RedactingFilter) em vez de
    resposta HTTP pública.
    """
    with caplog.at_level(logging.ERROR, logger="core.views"):
        api_client.get(reverse("core:health"))

    assert any(
        registro.exc_info and "Health check falhou" in registro.getMessage()
        for registro in caplog.records
    ), "a falha do banco não foi registrada em lugar nenhum"
