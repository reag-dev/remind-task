import pytest
from rest_framework.test import APIClient

PASSWORD = "Contrato!Vencendo#2026"


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def password():
    return PASSWORD


@pytest.fixture
def user(db, django_user_model):
    return django_user_model.objects.create_user(
        email="ana@example.com", name="Ana Souza", password=PASSWORD
    )


@pytest.fixture
def other_user(db, django_user_model):
    return django_user_model.objects.create_user(
        email="bruno@example.com", name="Bruno Lima", password=PASSWORD
    )


@pytest.fixture
def auth_client(api_client, user):
    """Client autenticado via JWT — o mesmo caminho que o frontend usaria."""
    from rest_framework_simplejwt.tokens import RefreshToken

    access = RefreshToken.for_user(user).access_token
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return api_client
