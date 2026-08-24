"""
O comando que o cron da plataforma executa.

Ele substitui o serviço `beat` — um processo ocioso 24 horas por dia para
disparar uma task a cada 15 minutos. O que precisa ficar travado é que ele
executa a varredura de VERDADE, e não a enfileira: um cron que enfileira sai com
sucesso antes de saber se o trabalho deu certo.
"""

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command

pytestmark = pytest.mark.django_db


def rodar():
    saida = StringIO()
    call_command("scan_alerts", stdout=saida)
    return saida.getvalue()


def test_roda_a_varredura_de_forma_sincrona():
    """
    Chamada direta, não `.delay()`.

    Se enfileirasse, o processo do cron sairia com sucesso tendo apenas
    entregado a mensagem — e uma falha no worker viraria alerta não enviado sem
    nada vermelho em lugar nenhum.
    """
    with patch("alerts.management.commands.scan_alerts.scan_due_records") as varredura:
        varredura.return_value = 0
        rodar()

    varredura.assert_called_once_with()


def test_informa_quantos_alertas_gerou():
    with patch("alerts.management.commands.scan_alerts.scan_due_records") as varredura:
        varredura.return_value = 7
        saida = rodar()

    assert "7" in saida


def test_tabela_sem_regra_nao_gera_nada(user):
    """Caminho real, com banco: sem regra ativa, a varredura sai em zero."""
    assert "0" in rodar()
