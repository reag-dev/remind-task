"""
Recuperação de senha (Phase 10).

O fluxo tem duas metades com riscos diferentes: pedir o link não pode contar
quais e-mails têm conta (isso está em `tests/security/test_user_enumeration.py`),
e consumir o link não pode deixar nada em aberto — nem o token, nem as sessões
que já existiam, nem o bloqueio do django-axes.
"""

import re

import pytest
from django.core import mail
from django.urls import reverse

pytestmark = pytest.mark.django_db

PEDIR = "accounts:password-reset"
CONFIRMAR = "accounts:password-reset-confirm"
SENHA_NOVA = "Vencimento!Contrato#2027"


def link_do_email():
    """O `uid` e o `token` do último e-mail enviado."""
    corpo = mail.outbox[-1].body
    achado = re.search(r"uid=([^&\s]+)&token=([^\s]+)", corpo)
    assert achado, f"nenhum link de recuperação no corpo:\n{corpo}"
    return {"uid": achado.group(1), "token": achado.group(2)}


@pytest.fixture
def link(api_client, user):
    api_client.post(reverse(PEDIR), {"email": user.email}, format="json")
    return link_do_email()


# ------------------------------------------------------------ pedir o link


def test_pedido_envia_um_email_com_link_para_a_spa(api_client, user, settings):
    settings.FRONTEND_URL = "https://front.exemplo"

    resposta = api_client.post(reverse(PEDIR), {"email": user.email}, format="json")

    assert resposta.status_code == 204
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [user.email]
    # O link aponta para a SPA, e não para a API: quem renderiza o formulário é
    # o frontend.
    assert "https://front.exemplo/redefinir-senha?uid=" in mail.outbox[0].body


def test_o_email_nao_carrega_senha_nem_dado_de_tabela(api_client, user):
    """RS05 — o e-mail sai do perímetro e fica na caixa do destinatário."""
    api_client.post(reverse(PEDIR), {"email": user.email}, format="json")

    corpo = mail.outbox[0].body
    for vazamento in ("Contrato!Vencendo#2026", "argon2", "pbkdf2"):
        assert vazamento not in corpo


def test_conta_inativa_nao_recebe_link(api_client, user):
    """
    Desativar uma conta precisa continuar sendo suficiente para tirá-la do ar.
    Sem o `is_active` no filtro, a recuperação seria a porta dos fundos.
    """
    user.is_active = False
    user.save(update_fields=["is_active"])

    resposta = api_client.post(reverse(PEDIR), {"email": user.email}, format="json")

    assert resposta.status_code == 204
    assert mail.outbox == []


def test_email_malformado_e_recusado(api_client):
    """Formato inválido é 400 — isso não conta nada sobre cadastro nenhum."""
    resposta = api_client.post(reverse(PEDIR), {"email": "nao-e-email"}, format="json")

    assert resposta.status_code == 400
    assert mail.outbox == []


# --------------------------------------------------------- consumir o link


def test_redefinir_troca_a_senha(api_client, user, link, password):
    resposta = api_client.post(
        reverse(CONFIRMAR), {**link, "password": SENHA_NOVA}, format="json"
    )

    assert resposta.status_code == 204

    user.refresh_from_db()
    assert user.check_password(SENHA_NOVA)
    assert not user.check_password(password)


def test_reset_token_cannot_be_reused(api_client, user, link):
    """
    Uso único sem tabela, sem coluna e sem rotina de expurgo.

    O `PasswordResetTokenGenerator` deriva o hash da senha ATUAL: trocar a senha
    muda o hash, e o mesmo token deixa de conferir. É a razão de não existir
    token próprio aqui.
    """
    primeira = api_client.post(
        reverse(CONFIRMAR), {**link, "password": SENHA_NOVA}, format="json"
    )
    segunda = api_client.post(
        reverse(CONFIRMAR), {**link, "password": "Outra!Senha#2027"}, format="json"
    )

    assert primeira.status_code == 204
    assert segunda.status_code == 400

    user.refresh_from_db()
    assert user.check_password(SENHA_NOVA)


def test_reset_blacklists_open_sessions(api_client, user, password):
    """
    RS07 no caso em que ele mais importa.

    Quem roubou um refresh continuaria dentro por 7 dias **justamente depois** de
    a vítima trocar a senha por suspeitar do roubo — o único momento em que ela
    acha que resolveu o problema.

    A ordem aqui não é enfeite: a sessão precisa existir ANTES do pedido do
    link. Ver `test_entrar_invalida_um_link_ja_pedido` para o porquê — logar
    depois de pedir o link queimaria o token.
    """
    login = api_client.post(
        reverse("accounts:login"),
        {"email": user.email, "password": password},
        format="json",
    )
    assert login.status_code == 200

    api_client.post(reverse(PEDIR), {"email": user.email}, format="json")
    link = link_do_email()

    api_client.post(reverse(CONFIRMAR), {**link, "password": SENHA_NOVA}, format="json")

    # O cookie de refresh continua no client; o que mudou é que o token não vale.
    renovacao = api_client.post(reverse("accounts:refresh"))
    assert renovacao.status_code == 401


def test_entrar_invalida_um_link_ja_pedido(api_client, user, password, link):
    """
    Consequência do token derivar de `last_login`, e ela não é óbvia.

    Quem pede o link, lembra a senha, entra normalmente e só depois clica no
    e-mail encontra "link inválido" — porque o login mexeu no `last_login` e o
    hash do token mudou. É o comportamento do `PasswordResetTokenGenerator` do
    Django, e é defensável (a sessão nova prova que o dono já está dentro), mas
    fica registrado aqui para não ser diagnosticado do zero como bug.
    """
    api_client.post(
        reverse("accounts:login"),
        {"email": user.email, "password": password},
        format="json",
    )

    resposta = api_client.post(
        reverse(CONFIRMAR), {**link, "password": SENHA_NOVA}, format="json"
    )

    assert resposta.status_code == 400


@pytest.mark.django_db(transaction=True)
def test_redefinir_limpa_o_bloqueio_do_axes(api_client, user):
    """
    Quem esqueceu a senha erra várias vezes ANTES de pedir o link.

    Com AXES_FAILURE_LIMIT=5, chegaria ao fim do fluxo com a senha nova em mãos
    e um 429 na cara, sem entender por quê.

    `transaction=True` é obrigatório: o login roda fora do ATOMIC_REQUESTS
    justamente para o `AccessAttempt` do axes sobreviver ao 401 (ver
    `accounts/urls.py`), e num teste em transação envolvente o contador não
    persistiria.
    """
    url_login = reverse("accounts:login")
    for _ in range(5):
        api_client.post(
            url_login, {"email": user.email, "password": "errada-porem-longa"}, format="json"
        )

    bloqueado = api_client.post(
        url_login, {"email": user.email, "password": "errada-porem-longa"}, format="json"
    )
    assert bloqueado.status_code == 429, "o cenário depende do bloqueio existir"

    api_client.post(reverse(PEDIR), {"email": user.email}, format="json")
    link = link_do_email()
    api_client.post(reverse(CONFIRMAR), {**link, "password": SENHA_NOVA}, format="json")

    depois = api_client.post(
        url_login, {"email": user.email, "password": SENHA_NOVA}, format="json"
    )
    assert depois.status_code == 200


@pytest.mark.parametrize("fraca", ["123", "senha", "ana@example.com"])
def test_a_senha_nova_passa_pelos_validadores_do_registro(api_client, user, link, fraca):
    """Uma recuperação que aceita senha fraca desfaz o cuidado do cadastro."""
    resposta = api_client.post(
        reverse(CONFIRMAR), {**link, "password": fraca}, format="json"
    )

    assert resposta.status_code == 400
    assert "password" in resposta.json()

    user.refresh_from_db()
    assert not user.check_password(fraca)


def test_token_de_outro_usuario_nao_serve(api_client, user, other_user, link):
    """O uid é do dono do token; trocar um sem o outro não passa."""
    from django.utils.encoding import force_bytes
    from django.utils.http import urlsafe_base64_encode

    resposta = api_client.post(
        reverse(CONFIRMAR),
        {
            "uid": urlsafe_base64_encode(force_bytes(other_user.pk)),
            "token": link["token"],
            "password": SENHA_NOVA,
        },
        format="json",
    )

    assert resposta.status_code == 400


def test_o_link_nao_sai_com_html_escapado(api_client, user):
    """
    O bug que este teste pegou na primeira execução.

    Sem `{% autoescape off %}`, o Django escapa o `&` do template para `&amp;` —
    o que num corpo `text/plain` não protege de nada e QUEBRA o link: o cliente
    de e-mail entrega ao frontend um parâmetro chamado `amp;token`, e o fluxo
    morre na tela de "link inválido" sem que ninguém entenda por quê.
    """
    api_client.post(reverse(PEDIR), {"email": user.email}, format="json")

    corpo = mail.outbox[0].body
    assert "&amp;" not in corpo
    assert "&token=" in corpo
