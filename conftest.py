import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

PASSWORD = "Contrato!Vencendo#2026"


@pytest.fixture(autouse=True)
def cache_limpo():
    """
    Zera o cache antes de cada teste.

    Os contadores de throttle vivem ali. Sem isto, um teste que faz muitas
    requisições deixa o contador cheio para o seguinte, e a suíte passa a
    depender da ORDEM de execução — o tipo de falha que aparece só quando
    alguém acrescenta um teste no meio, e some ao rodar o arquivo sozinho.
    """
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


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
def authenticate():
    """
    Fábrica de clients autenticados por JWT.

    Fábrica, e não fixture direta, porque os testes de isolamento (RS01) precisam
    de DOIS clients independentes na mesma execução.
    """

    def _make(user):
        client = APIClient()
        client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}"
        )
        return client

    return _make


@pytest.fixture
def auth_client(authenticate, user):
    return authenticate(user)


@pytest.fixture
def other_client(authenticate, other_user):
    return authenticate(other_user)


# ---------------------------------------------------------------- tabelas


@pytest.fixture
def table(db, user):
    from tables.models import Table

    return Table.objects.create(user=user, name="Contratos", alert_lead_days=3)


@pytest.fixture
def other_table(db, other_user):
    from tables.models import Table

    return Table.objects.create(user=other_user, name="Licenças")


@pytest.fixture
def columns(db, table):
    """Estrutura do exemplo da seção 7 da especificação."""
    from tables.models import Column, ColumnType

    specs = [
        ("Cliente", ColumnType.TEXT, {}),
        ("Contrato", ColumnType.TEXT, {"is_required": True}),
        ("Responsável", ColumnType.TEXT, {"is_sensitive": True}),
        ("Data de vencimento", ColumnType.DUE_DATE, {"is_required": True}),
        ("Status", ColumnType.SELECT, {"options": ["Ativo", "Encerrado"]}),
    ]
    return [
        Column.objects.create(table=table, name=name, type=type_, position=i, **extra)
        for i, (name, type_, extra) in enumerate(specs)
    ]


# ---------------------------------------------------------------- registros

# Linha válida para a estrutura da fixture `columns`.
VALID_ROW = {
    "cliente": "Empresa A",
    "contrato": "CT-001",
    "responsavel": "João",
    "data_de_vencimento": "2026-08-20",
    "status": "Ativo",
}


@pytest.fixture
def valid_row():
    return dict(VALID_ROW)


@pytest.fixture
def record(db, table, columns):
    from records.models import Record

    return Record.objects.create(table=table, data=dict(VALID_ROW))


@pytest.fixture
def other_record(db, other_table):
    from records.models import Record

    return Record.objects.create(table=other_table, data={})
