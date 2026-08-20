"""
Critério 5 da seção 10 — "senhas não são armazenadas em texto puro" (RS03).
"""

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.urls import reverse

pytestmark = pytest.mark.django_db

SENHA = "Contrato!Vencendo#2026"


def test_the_password_is_stored_as_an_argon2id_hash(django_user_model):
    user = django_user_model.objects.create_user(
        email="hash@example.com", name="Hash", password=SENHA
    )

    assert user.password.startswith("argon2$argon2id$")
    assert user.check_password(SENHA)


def test_the_plaintext_password_is_nowhere_in_the_users_row(django_user_model):
    """
    Olha a LINHA inteira no banco, não só a coluna `password`.

    Um `create_user` que gravasse a senha também num campo de perfil, ou um
    `last_login` que carregasse o payload, passariam batido numa asserção que
    só olhasse a coluna esperada.
    """
    user = django_user_model.objects.create_user(
        email="linha@example.com", name="Linha", password=SENHA
    )

    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM users WHERE id = %s", [str(user.id)])
        linha = cursor.fetchone()

    assert SENHA not in " ".join(str(campo) for campo in linha)


def test_no_endpoint_ever_answers_with_the_password(api_client, user, auth_client):
    """
    O hash também não sai.

    Devolver o hash não revela a senha, mas entrega o algoritmo, o salt e os
    parâmetros de custo para quem quiser atacar offline — e não serve para nada
    do lado do cliente.
    """
    respostas = [
        api_client.post(
            reverse("accounts:register"),
            {
                "email": "novo@example.com",
                "name": "Novo",
                "password": SENHA,
                "password_confirm": SENHA,
            },
            format="json",
        ),
        api_client.post(
            reverse("accounts:login"), {"email": user.email, "password": SENHA}, format="json"
        ),
        auth_client.get(reverse("accounts:me")),
    ]

    for response in respostas:
        corpo = str(response.data)
        assert SENHA not in corpo
        assert "argon2" not in corpo
        assert "password" not in response.data


def test_a_weak_password_is_refused_before_it_is_ever_stored(api_client):
    """
    Hash forte não salva senha fraca. Os validadores são parte do critério.
    """
    response = api_client.post(
        reverse("accounts:register"),
        {
            "email": "fraca@example.com",
            "name": "Fraca",
            "password": "12345678",
            "password_confirm": "12345678",
        },
        format="json",
    )

    assert response.status_code == 400
    assert not get_user_model().objects.filter(email="fraca@example.com").exists()
