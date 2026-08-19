import pytest
from django.db import IntegrityError, transaction
from django.urls import reverse

pytestmark = pytest.mark.django_db

REGISTER = reverse("accounts:register")
LOGIN = reverse("accounts:login")
REFRESH = reverse("accounts:refresh")
LOGOUT = reverse("accounts:logout")
ME = reverse("accounts:me")

STRONG = "Contrato!Vencendo#2026"


# ---------------------------------------------------------------- RF01 cadastro


def test_register_creates_user(api_client, django_user_model):
    response = api_client.post(
        REGISTER,
        {"email": "novo@example.com", "name": "Novo", "password": STRONG},
        format="json",
    )

    assert response.status_code == 201
    assert django_user_model.objects.filter(email="novo@example.com").exists()
    # A senha nunca volta no corpo, nem write_only vazando por engano.
    assert "password" not in response.data


def test_register_never_stores_plaintext_password(api_client, django_user_model):
    api_client.post(
        REGISTER,
        {"email": "hash@example.com", "name": "Hash", "password": STRONG},
        format="json",
    )

    user = django_user_model.objects.get(email="hash@example.com")
    assert user.password.startswith("argon2$")  # RS03
    assert STRONG not in user.password
    assert user.check_password(STRONG)


def test_register_normalizes_email_case(api_client, django_user_model):
    response = api_client.post(
        REGISTER,
        {"email": "MAIUSCULA@Example.COM", "name": "X", "password": STRONG},
        format="json",
    )

    assert response.status_code == 201
    assert django_user_model.objects.get(name="X").email == "maiuscula@example.com"


@pytest.mark.parametrize(
    "weak",
    [
        "curta1",              # abaixo de 10 caracteres
        "12345678901234",      # só dígitos
        "password123",         # senha comum
    ],
)
def test_register_rejects_weak_password(api_client, weak):
    response = api_client.post(
        REGISTER,
        {"email": "fraca@example.com", "name": "Fraca", "password": weak},
        format="json",
    )

    assert response.status_code == 400
    assert "password" in response.data


def test_register_rejects_password_similar_to_email(api_client):
    response = api_client.post(
        REGISTER,
        {"email": "joaopedro@example.com", "name": "Joao", "password": "joaopedro@example.com"},
        format="json",
    )

    assert response.status_code == 400


def test_duplicate_email_is_blocked_by_the_database_case_insensitively(
    django_user_model, user
):
    """
    A unicidade case-insensitive é da collation, não do serializer.

    Este teste vai direto ao manager: mesmo pulando a camada de API, o Postgres
    recusa Ana@Example.com quando ana@example.com já existe.
    """
    with pytest.raises(IntegrityError), transaction.atomic():
        django_user_model.objects.create(
            email="Ana@Example.COM", name="Impostora", password="x"
        )


# ---------------------------------------------------------------- RF02 login


def test_login_returns_access_and_sets_httponly_refresh_cookie(api_client, user):
    response = api_client.post(
        LOGIN, {"email": user.email, "password": STRONG}, format="json"
    )

    assert response.status_code == 200
    assert "access" in response.data
    assert response.data["user"]["email"] == user.email

    # RS07: o refresh NÃO pode voltar no corpo — só em cookie inacessível ao JS.
    assert "refresh" not in response.data

    cookie = response.cookies["refresh_token"]
    assert cookie["httponly"] is True
    assert cookie["samesite"] == "Lax"
    assert cookie["path"] == "/api/auth/"


def test_login_accepts_email_in_any_case(api_client, user):
    response = api_client.post(
        LOGIN, {"email": "ANA@EXAMPLE.COM", "password": STRONG}, format="json"
    )

    assert response.status_code == 200


# Os testes de login que FALHAM precisam de transação real (transaction=True).
#
# Com o wrapper transacional padrão do pytest-django, a request roda dentro de um
# atomic block que não existe em produção — o endpoint de login é non_atomic. O
# set_rollback() do DRF checa `in_atomic_block`, então no teste ele envenenaria a
# transação do próprio teste, enquanto em produção é no-op. transaction=True
# reproduz a semântica real.
real_transaction = pytest.mark.django_db(transaction=True)


@real_transaction
def test_login_with_wrong_password_fails(api_client, user):
    response = api_client.post(
        LOGIN, {"email": user.email, "password": "senha-errada-mas-longa"}, format="json"
    )

    assert response.status_code == 401


@real_transaction
def test_login_of_inactive_user_fails(api_client, user):
    user.is_active = False
    user.save(update_fields=["is_active"])

    response = api_client.post(
        LOGIN, {"email": user.email, "password": STRONG}, format="json"
    )

    assert response.status_code == 401


# ---------------------------------------------------------------- RS07 sessão


def test_refresh_reads_cookie_and_rotates_the_token(api_client, user):
    login = api_client.post(LOGIN, {"email": user.email, "password": STRONG}, format="json")
    original = login.cookies["refresh_token"].value

    response = api_client.post(REFRESH, {}, format="json")

    assert response.status_code == 200
    assert "access" in response.data
    assert "refresh" not in response.data
    assert response.cookies["refresh_token"].value != original  # rotacionou


def test_rotated_refresh_token_goes_to_the_blacklist(api_client, user):
    login = api_client.post(LOGIN, {"email": user.email, "password": STRONG}, format="json")
    original = login.cookies["refresh_token"].value

    api_client.post(REFRESH, {}, format="json")

    # Reapresentar o token antigo explicitamente deve falhar.
    replay = api_client.post(REFRESH, {"refresh": original}, format="json")
    assert replay.status_code == 401


def test_refresh_without_token_is_unauthorized(api_client):
    assert api_client.post(REFRESH, {}, format="json").status_code == 401


def test_logout_blacklists_the_refresh_token_and_clears_the_cookie(api_client, user):
    login = api_client.post(LOGIN, {"email": user.email, "password": STRONG}, format="json")
    issued = login.cookies["refresh_token"].value

    response = api_client.post(LOGOUT, {}, format="json")
    assert response.status_code == 204
    assert response.cookies["refresh_token"].value == ""

    # O token entregue no login não vale mais.
    assert api_client.post(REFRESH, {"refresh": issued}, format="json").status_code == 401


def test_logout_is_idempotent(api_client, user):
    api_client.post(LOGIN, {"email": user.email, "password": STRONG}, format="json")

    assert api_client.post(LOGOUT, {}, format="json").status_code == 204
    assert api_client.post(LOGOUT, {}, format="json").status_code == 204


# ---------------------------------------------------------------- RS03 axes


@real_transaction
def test_failed_login_attempt_survives_the_request(api_client, user):
    """
    Regressão: com ATOMIC_REQUESTS=True, o set_rollback() do DRF ao tratar o 401
    reverte a request inteira — inclusive o AccessAttempt do axes. O contador
    ficava sempre em zero e o bloqueio nunca disparava. O login roda fora da
    transação por causa disso (ver accounts/urls.py).
    """
    from axes.models import AccessAttempt

    api_client.post(
        LOGIN, {"email": user.email, "password": "errada-porem-longa"}, format="json"
    )

    assert AccessAttempt.objects.count() == 1


@real_transaction
def test_login_is_locked_after_repeated_failures(api_client, user):
    for _ in range(5):
        api_client.post(
            LOGIN, {"email": user.email, "password": "errada-porem-longa"}, format="json"
        )

    blocked = api_client.post(
        LOGIN, {"email": user.email, "password": "errada-porem-longa"}, format="json"
    )
    assert blocked.status_code == 429  # axes 7 usa 429 Too Many Requests

    # A propriedade que importa: nem a senha CORRETA passa durante o bloqueio.
    with_correct_password = api_client.post(
        LOGIN, {"email": user.email, "password": STRONG}, format="json"
    )
    assert with_correct_password.status_code == 429


# ---------------------------------------------------------------- /me


def test_me_requires_authentication(api_client):
    assert api_client.get(ME).status_code == 401


def test_me_returns_the_requesting_user(auth_client, user):
    response = auth_client.get(ME)

    assert response.status_code == 200
    assert response.data["email"] == user.email
    assert response.data["id"] == str(user.id)


def test_me_updates_timezone(auth_client, user):
    response = auth_client.patch(ME, {"timezone": "Europe/Lisbon"}, format="json")

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.timezone == "Europe/Lisbon"


def test_me_rejects_invalid_timezone(auth_client):
    response = auth_client.patch(ME, {"timezone": "Marte/Olympus"}, format="json")

    assert response.status_code == 400
    assert "timezone" in response.data


def test_me_cannot_change_email(auth_client, user):
    auth_client.patch(ME, {"email": "outro@example.com"}, format="json")

    user.refresh_from_db()
    assert user.email == "ana@example.com"
