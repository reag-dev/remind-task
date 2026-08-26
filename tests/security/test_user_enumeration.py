"""
O fluxo de recuperação não pode virar verificador de cadastro (Phase 10).

Um endpoint que responde diferente para "e-mail com conta" e "e-mail sem conta"
é um oráculo: basta varrer uma lista de endereços e ler os códigos de resposta
para saber quem usa o sistema. O mesmo raciocínio do RS04, que devolve 404 em
vez de 403 justamente para não confirmar que um recurso existe.

As comparações abaixo são byte a byte, e não "os dois são 204": o dia em que
alguém acrescentar um corpo de resposta — uma mensagem amigável, um campo de
diagnóstico — a diferença aparece aqui antes de aparecer para quem sonda.
"""

import pytest
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

pytestmark = pytest.mark.django_db

PEDIR = reverse("accounts:password-reset")
CONFIRMAR = reverse("accounts:password-reset-confirm")
LOGIN = reverse("accounts:login")

DESCONHECIDO = "ninguem-tem-esta-conta@example.com"


def pedir(api_client, email):
    return api_client.post(PEDIR, {"email": email}, format="json")


def test_pedir_link_responde_igual_com_e_sem_conta(api_client, user):
    com_conta = pedir(api_client, user.email)
    sem_conta = pedir(api_client, DESCONHECIDO)

    assert com_conta.status_code == sem_conta.status_code == 204
    assert com_conta.content == sem_conta.content == b""


def test_conta_inativa_nao_se_distingue_de_conta_inexistente(api_client, user):
    """
    Desativada também não pode vazar.

    Sem isto, quem sonda descobriria não só quem tem conta, mas quem TEVE — o
    que é informação sobre a pessoa, não sobre o sistema.
    """
    user.is_active = False
    user.save(update_fields=["is_active"])

    inativa = pedir(api_client, user.email)
    inexistente = pedir(api_client, DESCONHECIDO)

    assert inativa.status_code == inexistente.status_code == 204
    assert inativa.content == inexistente.content == b""


def test_confirmar_responde_igual_para_uid_desconhecido_e_token_errado(api_client, user):
    """
    A segunda metade do fluxo tem o mesmo risco.

    Separar "esse uid não existe" de "esse token não confere" contaria, de novo,
    quais contas existem — desta vez para quem já tem um link nas mãos e quer
    saber se um id qualquer corresponde a alguém.
    """
    uid_real = urlsafe_base64_encode(force_bytes(user.pk))
    uid_falso = urlsafe_base64_encode(force_bytes("00000000-0000-0000-0000-000000000000"))
    senha = "Vencimento!Contrato#2027"

    token_errado = api_client.post(
        CONFIRMAR, {"uid": uid_real, "token": "nao-confere", "password": senha}, format="json"
    )
    uid_inexistente = api_client.post(
        CONFIRMAR, {"uid": uid_falso, "token": "nao-confere", "password": senha}, format="json"
    )
    uid_ilegivel = api_client.post(
        CONFIRMAR, {"uid": "$$$ nao e base64 $$$", "token": "nao-confere", "password": senha},
        format="json",
    )

    assert token_errado.status_code == 400
    assert uid_inexistente.status_code == 400
    assert uid_ilegivel.status_code == 400
    assert token_errado.content == uid_inexistente.content == uid_ilegivel.content


@pytest.mark.django_db(transaction=True)
def test_login_nao_distingue_senha_errada_de_conta_inexistente(api_client, user):
    """
    A porta mais óbvia, conferida junto porque é o mesmo ataque.

    Se o login respondesse "usuário não encontrado" para um caso e "senha
    inválida" para o outro, o endpoint de recuperação teria sido endurecido à
    toa — o oráculo estaria ao lado.

    `transaction=True` porque o login roda fora do ATOMIC_REQUESTS, para o
    AccessAttempt do django-axes sobreviver ao 401 (ver accounts/urls.py).
    """
    senha_errada = api_client.post(
        LOGIN, {"email": user.email, "password": "errada-porem-longa"}, format="json"
    )
    sem_conta = api_client.post(
        LOGIN, {"email": DESCONHECIDO, "password": "errada-porem-longa"}, format="json"
    )

    assert senha_errada.status_code == sem_conta.status_code
    assert senha_errada.content == sem_conta.content
