"""
Exclusão de conta (Phase 11).

O que precisa ser verdade depois de `DELETE /api/auth/me/`:

1. só acontece com a senha atual na mão — token roubado não apaga conta;
2. o que era do usuário sai INTEIRO (cascade), e o que era de outro não é
   tocado;
3. as sessões morrem por decisão, não por acaso — `OutstandingToken.user` é
   SET_NULL, então sem blacklist explícita os refresh ficam órfãos e válidos;
4. o dono fica sabendo, por e-mail, com o tamanho do estrago.
"""

from datetime import date

import pytest
from django.core import mail
from django.urls import reverse

from alerts.models import Alert, AlertRule, AlertStatus
from records.models import Record
from tables.models import Table

pytestmark = pytest.mark.django_db

ME = reverse("accounts:me")


@pytest.fixture
def conta_com_dados(user, table, columns, record):
    """Usuário com uma linha em cada uma das tabelas que o cascade deve levar."""
    regra = AlertRule.objects.create(table=table, offset_days=3)
    Alert.objects.create(
        record=record,
        rule=regra,
        user=user,
        trigger_date=date(2026, 8, 20),
        due_date_snapshot=date(2026, 8, 23),
        status=AlertStatus.PENDING,
    )
    return user


# ------------------------------------------------------- a senha é exigida


def test_sem_senha_nao_apaga(auth_client, user):
    resposta = auth_client.delete(ME, {}, format="json")

    assert resposta.status_code == 400
    assert "password" in resposta.json()
    assert type(user).objects.filter(pk=user.pk).exists()


def test_senha_errada_nao_apaga(auth_client, user):
    """
    O ponto da reautenticação.

    O access token vale 15 minutos e viaja em toda requisição; um token roubado
    já é ruim, mas recuperável — o dono troca a senha e o RS07 corta as sessões.
    Apagar a conta não é recuperável.
    """
    resposta = auth_client.delete(ME, {"password": "nao-e-a-senha"}, format="json")

    assert resposta.status_code == 400
    assert "password" in resposta.json()
    assert type(user).objects.filter(pk=user.pk).exists()


def test_anonimo_nao_apaga(api_client):
    assert api_client.delete(ME, {"password": "seja-la-o-que-for"}, format="json").status_code == 401


# ------------------------------------------------------------ o caminho feliz


def test_apaga_a_conta_com_a_senha_correta(auth_client, user, password):
    resposta = auth_client.delete(ME, {"password": password}, format="json")

    assert resposta.status_code == 204
    assert not type(user).objects.filter(pk=user.pk).exists()


def test_deletion_leaves_other_user_intact(
    authenticate, conta_com_dados, other_user, other_table, other_record, password
):
    """
    A contraprova do cascade: apagar A não pode levar nada de B.

    Contagem nas cinco tabelas, com os dois usuários presentes — sem o segundo,
    um cascade largo demais passaria despercebido, porque não haveria nada de
    ninguém para sobrar.
    """
    AlertRule.objects.create(table=other_table, offset_days=1)

    antes = {
        "tables": Table.objects.count(),
        "records": Record.objects.count(),
        "rules": AlertRule.objects.count(),
        "alerts": Alert.objects.count(),
    }

    resposta = authenticate(conta_com_dados).delete(ME, {"password": password}, format="json")
    assert resposta.status_code == 204

    # Do usuário apagado: nada. Do outro: tudo.
    assert Table.objects.filter(user=conta_com_dados).count() == 0
    assert Record.objects.filter(user=conta_com_dados).count() == 0
    assert AlertRule.objects.filter(user=conta_com_dados).count() == 0
    assert Alert.objects.filter(user=conta_com_dados).count() == 0

    assert Table.objects.filter(user=other_user).count() == antes["tables"] - 1
    assert Record.objects.filter(user=other_user).count() == antes["records"] - 1
    assert AlertRule.objects.filter(user=other_user).count() == antes["rules"] - 1
    assert Alert.objects.filter(user=other_user).count() == antes["alerts"]
    assert type(other_user).objects.filter(pk=other_user.pk).exists()


# ------------------------------------------------------------- as sessões


def test_apagar_a_conta_invalida_os_refresh_em_aberto(auth_client, user, password):
    """
    RS07 — `OutstandingToken.user` é SET_NULL, não CASCADE.

    Sem a blacklist explícita, os refresh viram linhas órfãs com `user_id = NULL`,
    criptograficamente válidas até expirarem. Na prática o acesso já falharia,
    porque a busca do usuário pelo claim não acha ninguém — mas confiar nisso
    contraria o RS07, que fez o logout usar blacklist justamente para "sair"
    significar alguma coisa em vez de depender do acaso.
    """
    from rest_framework_simplejwt.token_blacklist.models import (
        BlacklistedToken,
        OutstandingToken,
    )
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken.for_user(user)
    emitidos = OutstandingToken.objects.filter(user=user).count()
    assert emitidos > 0, "o cenário depende de haver refresh em aberto"

    auth_client.delete(ME, {"password": password}, format="json")

    # As linhas sobrevivem ao usuário (SET_NULL), e é por isso que a blacklist
    # precisa ser feita ANTES: depois do delete o vínculo já não existe.
    assert BlacklistedToken.objects.filter(token__jti=refresh["jti"]).exists()


# ------------------------------------------------------------------ o aviso


def test_avisa_por_email_o_que_foi_apagado(
    auth_client, conta_com_dados, password, django_capture_on_commit_callbacks
):
    """
    O e-mail sai no `on_commit`, e o teste precisa disparar os callbacks.

    Com ATOMIC_REQUESTS a exclusão só é definitiva no commit da request. Enviar
    antes deixaria a porta aberta para o pior aviso possível: "sua conta foi
    excluída" chegando a quem ainda tem conta, porque algo depois deu rollback.
    """
    with django_capture_on_commit_callbacks(execute=True):
        resposta = auth_client.delete(ME, {"password": password}, format="json")

    assert resposta.status_code == 204
    assert len(mail.outbox) == 1

    aviso = mail.outbox[0]
    assert aviso.to == [conta_com_dados.email]
    # Contagens, não conteúdo.
    assert "tabelas ...... 1" in aviso.body
    assert "registros .... 1" in aviso.body
    assert "alertas ...... 1" in aviso.body


def test_o_aviso_nao_carrega_conteudo_de_registro(
    auth_client, conta_com_dados, password, django_capture_on_commit_callbacks
):
    """RS05 — o corpo de um registro nunca sai por e-mail, nem num aviso."""
    with django_capture_on_commit_callbacks(execute=True):
        auth_client.delete(ME, {"password": password}, format="json")

    corpo = mail.outbox[0].body
    for vazamento in ("Empresa A", "CT-001", "João"):
        assert vazamento not in corpo


def test_nao_avisa_quando_a_senha_esta_errada(auth_client, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        auth_client.delete(ME, {"password": "nao-e-a-senha"}, format="json")

    assert mail.outbox == []
