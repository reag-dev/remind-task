"""
Entrega dos alertas de e-mail: a transição `PENDING → SENT/FAILED`.

O que estes testes protegem, em ordem de gravidade:

1. **E-mail duplicado.** Um lembrete que chega duas vezes destrói a confiança no
   sistema mais rápido que um que não chega.
2. **Fila infinita.** Um endereço que não existe seria retentado a cada 15
   minutos para sempre, sem o limite de tentativas.
3. **Rajada contra provedor caído.** Sem backoff, a primeira execução depois de
   uma queda repetiria tudo de uma vez.

O backend de e-mail nos testes é o `locmem`, que o pytest-django instala
sozinho — daí a fixture `mailoutbox`. Ele aceita qualquer endereço, então o que
se mede aqui é a MÁQUINA DE ESTADOS, não a entrega de verdade. A entrega real
depende do domínio verificado no provedor, e nada em teste revela isso.
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from alerts.emails import enviar
from alerts.models import Alert, AlertChannel, AlertRule, AlertStatus
from alerts.services import generate_for_user
from alerts.tasks import send_pending_emails
from alerts.tests.conftest import TODAY

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def regra_de_email(alert_table):
    """Troca a regra in-app padrão por uma de e-mail no dia do vencimento."""
    alert_table.alert_rules.all().delete()
    return AlertRule.objects.create(
        table=alert_table, offset_days=0, channel=AlertChannel.EMAIL
    )


@pytest.fixture
def pendente(user, regra_de_email, make_record):
    make_record(TODAY)
    generate_for_user(user, TODAY)
    return Alert.objects.get()


# ------------------------------------------------------------ caminho normal


def test_entrega_marca_como_enviado(pendente, mailoutbox):
    desfechos = send_pending_emails()

    pendente.refresh_from_db()
    assert desfechos == {"enviados": 1, "falhos": 0, "adiados": 0}
    assert pendente.status == AlertStatus.SENT
    assert pendente.notified_at is not None
    assert pendente.delivery_attempts == 1
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == [pendente.user.email]


def test_rodar_de_novo_nao_reenvia(pendente, mailoutbox):
    """
    A garantia contra duplicata, do lado simples: o alerta saiu de PENDING.

    O cron roda a cada 15 minutos e não sabe o que a execução anterior fez — a
    consulta de candidatos é quem tem que excluir o que já foi entregue.
    """
    send_pending_emails()
    send_pending_emails()

    assert len(mailoutbox) == 1


def test_alerta_in_app_nao_vira_email(user, alert_table, make_record, mailoutbox):
    """
    A regra in-app entrega no ato e nasce SENT, então nem chega à fila. Este
    teste existe para o caso de alguém afrouxar o filtro de canal na consulta
    de candidatos.
    """
    make_record(TODAY)
    generate_for_user(user, TODAY)

    send_pending_emails()

    assert Alert.objects.filter(status=AlertStatus.SENT).exists()
    assert mailoutbox == []


def test_conta_desativada_nao_recebe(pendente, mailoutbox):
    """Desativar um usuário tem que parar o e-mail, não só o login."""
    usuario = pendente.user
    usuario.is_active = False
    usuario.save(update_fields=["is_active"])

    desfechos = send_pending_emails()

    pendente.refresh_from_db()
    assert mailoutbox == []
    assert desfechos["enviados"] == 0
    assert pendente.status == AlertStatus.PENDING


# ------------------------------------------------------------------- falha


def test_falha_conta_a_tentativa_e_mantem_pendente(pendente, mailoutbox):
    """
    Provedor fora do ar é situação TRANSITÓRIA. Marcar FAILED na primeira falha
    perderia o aviso por causa de um soluço de rede.
    """
    with patch("alerts.tasks.enviar", side_effect=OSError("conexão recusada")):
        desfechos = send_pending_emails()

    pendente.refresh_from_db()
    assert desfechos == {"enviados": 0, "falhos": 1, "adiados": 0}
    assert pendente.status == AlertStatus.PENDING
    assert pendente.delivery_attempts == 1
    assert pendente.last_attempt_at is not None
    assert pendente.notified_at is None
    assert mailoutbox == []


def test_desiste_no_limite_de_tentativas(pendente, settings):
    """
    O outro lado: um endereço que não existe não pode ser retentado para sempre.

    Chegando ao limite, o alerta vira FAILED — que sai da consulta de candidatos
    e para a fila.
    """
    settings.EMAIL_MAX_ATTEMPTS = 2
    # Sem espera entre as tentativas, senão o backoff adiaria a segunda.
    settings.EMAIL_RETRY_BASE_MINUTES = 0

    with patch("alerts.tasks.enviar", side_effect=OSError("caixa inexistente")):
        send_pending_emails()
        pendente.refresh_from_db()
        assert pendente.status == AlertStatus.PENDING, "desistiu cedo demais"

        send_pending_emails()

    pendente.refresh_from_db()
    assert pendente.status == AlertStatus.FAILED
    assert pendente.delivery_attempts == 2


def test_alerta_que_falhou_de_vez_sai_da_fila(pendente, settings, mailoutbox):
    settings.EMAIL_MAX_ATTEMPTS = 1
    with patch("alerts.tasks.enviar", side_effect=OSError("caixa inexistente")):
        send_pending_emails()

    pendente.refresh_from_db()
    assert pendente.status == AlertStatus.FAILED

    # Agora com o envio funcionando: não pode ressuscitar.
    desfechos = send_pending_emails()

    assert desfechos["enviados"] == 0
    assert mailoutbox == []


# ------------------------------------------------------------------ backoff


def test_a_segunda_tentativa_espera(pendente, mailoutbox, settings):
    """
    Sem backoff, a execução seguinte do cron repetiria a rajada contra um
    provedor que já está caído — exatamente quando ele menos aguenta.
    """
    settings.EMAIL_RETRY_BASE_MINUTES = 30

    with patch("alerts.tasks.enviar", side_effect=OSError("fora do ar")):
        send_pending_emails()

    # Provedor voltou, mas a espera ainda não venceu.
    desfechos = send_pending_emails()

    pendente.refresh_from_db()
    assert desfechos == {"enviados": 0, "falhos": 0, "adiados": 1}
    assert pendente.delivery_attempts == 1, "tentou de novo antes da hora"
    assert mailoutbox == []


def test_passada_a_espera_tenta_de_novo(pendente, mailoutbox, settings):
    settings.EMAIL_RETRY_BASE_MINUTES = 30

    with patch("alerts.tasks.enviar", side_effect=OSError("fora do ar")):
        send_pending_emails()

    # Recua o carimbo em vez de avançar o relógio: é a mesma condição, sem
    # depender de congelar o tempo em código que usa `timezone.now()` em três
    # lugares diferentes.
    Alert.objects.filter(pk=pendente.pk).update(
        last_attempt_at=timezone.now() - timedelta(minutes=31)
    )

    desfechos = send_pending_emails()

    pendente.refresh_from_db()
    assert desfechos["enviados"] == 1
    assert pendente.status == AlertStatus.SENT
    assert pendente.delivery_attempts == 2
    assert len(mailoutbox) == 1


def test_a_espera_dobra_a_cada_tentativa(pendente, settings):
    """
    2, 4, 8, 16 minutos — e não um intervalo fixo.

    Com intervalo fixo, uma indisponibilidade de horas produz dezenas de
    tentativas idênticas. Dobrando, o mesmo período produz poucas.
    """
    settings.EMAIL_RETRY_BASE_MINUTES = 2
    settings.EMAIL_MAX_ATTEMPTS = 9

    with patch("alerts.tasks.enviar", side_effect=OSError("fora do ar")):
        send_pending_emails()  # tentativa 1

        # Depois da 1ª, a espera é de 2 minutos: 3 já passaram.
        Alert.objects.filter(pk=pendente.pk).update(
            last_attempt_at=timezone.now() - timedelta(minutes=3)
        )
        send_pending_emails()  # tentativa 2
        pendente.refresh_from_db()
        assert pendente.delivery_attempts == 2

        # Depois da 2ª, a espera dobrou para 4: os mesmos 3 minutos não bastam.
        Alert.objects.filter(pk=pendente.pk).update(
            last_attempt_at=timezone.now() - timedelta(minutes=3)
        )
        send_pending_emails()

    pendente.refresh_from_db()
    assert pendente.delivery_attempts == 2, "a espera não dobrou"


# ------------------------------------------------------- a fila não desaba


def test_um_alerta_problematico_nao_para_os_outros(
    user, regra_de_email, make_record, mailoutbox
):
    """
    Mesma regra que a varredura aplica por usuário: um item estragado não pode
    levar a fila junto.
    """
    make_record(TODAY)
    make_record(TODAY, cliente="Empresa B")
    generate_for_user(user, TODAY)
    assert Alert.objects.count() == 2

    chamadas = {"n": 0}

    def falha_na_primeira(alert):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise RuntimeError("erro inesperado montando a mensagem")
        return enviar(alert)

    with patch("alerts.tasks.enviar", side_effect=falha_na_primeira):
        desfechos = send_pending_emails()

    assert desfechos["enviados"] == 1
    assert desfechos["falhos"] == 1
    assert len(mailoutbox) == 1
