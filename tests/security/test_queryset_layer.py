"""
A PRIMEIRA barreira, testada com a segunda fora de cena.

Por que este arquivo existe: apagar `filter(user=self.request.user)` de
`TableViewSet.get_queryset()` **não quebra nenhum outro teste desta suíte**. E
não deveria mesmo — a RLS da Phase 7 filtra a mesma consulta no banco, então o
resultado observável pela API continua correto. É defesa em profundidade
funcionando.

Mas é também erosão silenciosa: a camada 1 pode sumir inteira sem sinal, e o dia
em que a RLS for desligada por qualquer motivo — um comando de management, um job
que esqueceu de entrar no contexto, um `SET LOCAL` que não pegou — o sistema fica
sem nenhuma barreira de uma vez.

O truque para isolar: `force_authenticate` injeta o usuário direto no request e
**pula as classes de autenticação** — que são justamente onde `core.rls.enter`
rebaixa a conexão. A consulta roda como dono, sem policy nenhuma valendo, e sobra
só o que o `get_queryset()` faz por conta própria. Cada teste confere esse
pressuposto antes de afirmar qualquer coisa.
"""

import pytest
from django.db import connection, transaction
from rest_framework.test import APIRequestFactory, force_authenticate

from alerts.views import AlertViewSet
from core import rls
from records.views import RecordViewSet
from tables.views import TableViewSet

pytestmark = pytest.mark.django_db

factory = APIRequestFactory()


def sem_rls_ativa():
    """A conexão está no papel de login, então nenhuma policy está filtrando."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_user")
        return cursor.fetchone()[0] != rls.RUNTIME_ROLE


def chamar(view_class, action, user, **kwargs):
    request = factory.get("/")
    force_authenticate(request, user=user)
    response = view_class.as_view(action)(request, **kwargs)

    if connection.needs_rollback:
        # Um 404 passa pelo exception_handler do DRF, que chama set_rollback() e
        # deixa a transação envenenada — nenhuma consulta roda depois disso. Aqui
        # dá para limpar a marca: a transação do teste vai ser descartada
        # inteira no fim, e só falta uma leitura de `current_user`.
        transaction.set_rollback(False)

    assert sem_rls_ativa(), (
        "a RLS estava ativa — este teste mediria a segunda barreira, não a primeira"
    )
    return response


def test_the_table_queryset_alone_excludes_other_owners(mine, theirs):
    response = chamar(TableViewSet, {"get": "list"}, mine.user)

    assert [t["id"] for t in response.data["results"]] == [str(mine.table.id)]


def test_the_table_detail_alone_refuses_a_foreign_id(mine, theirs):
    response = chamar(TableViewSet, {"get": "retrieve"}, mine.user, pk=theirs.table.id)

    assert response.status_code == 404


def test_the_record_queryset_alone_refuses_a_foreign_table(mine, theirs):
    response = chamar(
        RecordViewSet, {"get": "list"}, mine.user, table_id=theirs.table.id
    )

    assert response.status_code == 404


def test_the_record_queryset_alone_returns_only_the_owners_rows(mine, theirs):
    response = chamar(RecordViewSet, {"get": "list"}, mine.user, table_id=mine.table.id)

    assert [r["id"] for r in response.data["results"]] == [str(mine.record.id)]


def test_the_alert_inbox_alone_returns_only_the_owners_alerts(mine, theirs):
    response = chamar(AlertViewSet, {"get": "list"}, mine.user)

    assert [a["id"] for a in response.data["results"]] == [str(mine.alert.id)]
