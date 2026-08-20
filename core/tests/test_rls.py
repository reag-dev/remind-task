"""
RS01 — a segunda barreira de isolamento, dentro do Postgres.

Todo teste aqui consulta SEM filtro por usuário (`Record.objects.all()`,
`Table.objects.count()`). É de propósito: o que está sob teste não é o
`get_queryset()` das views — esse é o assunto dos testes de cross-tenant da API
— e sim o que sobra de proteção quando alguém esquece o filtro.
"""

from datetime import date

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import Error, connection, transaction
from django.urls import reverse

from alerts.models import Alert, AlertRule
from core import rls
from records.models import Record
from tables.models import Column, ColumnType, Table

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------- pré-condição


def test_runtime_role_cannot_bypass_rls(user):
    """
    Sem isto o resto do arquivo poderia passar por acidente.

    Superusuário e papel com BYPASSRLS ignoram policies em silêncio. Se o
    `SET LOCAL ROLE` falhasse, as consultas continuariam rodando como dono, e
    cada asserção de isolamento abaixo estaria apenas medindo o filtro do ORM.
    """
    with rls.session(user.id), connection.cursor() as cursor:
        cursor.execute("SELECT current_user")
        assert cursor.fetchone()[0] == rls.RUNTIME_ROLE

        cursor.execute(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
        )
        assert cursor.fetchone() == (False, False)


def test_connection_returns_to_the_login_role_after_the_block(user):
    with rls.session(user.id):
        pass

    with connection.cursor() as cursor:
        cursor.execute("SELECT current_user")
        assert cursor.fetchone()[0] != rls.RUNTIME_ROLE


def test_enter_outside_a_transaction_fails_loudly(monkeypatch):
    """
    Fora de transação o `SET LOCAL` viraria um WARNING do Postgres e não
    aplicaria nada — o pior desfecho possível, porque as consultas seguiriam
    funcionando sem isolamento e sem nada no log denunciando.
    """
    monkeypatch.setattr(connection, "in_atomic_block", False)

    with pytest.raises(ImproperlyConfigured):
        rls.enter("00000000-0000-0000-0000-000000000000")


# ---------------------------------------------------------------- leitura


def test_unfiltered_record_scan_sees_only_the_owner(record, other_record, user):
    with rls.session(user.id):
        visible = set(Record.objects.values_list("id", flat=True))

    assert visible == {record.id}


def test_unfiltered_table_scan_sees_only_the_owner(table, other_table, user):
    with rls.session(user.id):
        visible = set(Table.objects.values_list("id", flat=True))

    assert visible == {table.id}


def test_columns_follow_the_owning_table(columns, other_table, user):
    """`columns` não tem dono próprio: a policy vai por EXISTS na tabela-mãe."""
    intruder = Column.objects.create(
        table=other_table, name="Órgão", type=ColumnType.TEXT, position=0
    )

    with rls.session(user.id):
        visible = set(Column.objects.values_list("id", flat=True))

    assert visible == {column.id for column in columns}
    assert intruder.id not in visible


def test_alert_rules_and_alerts_are_isolated(record, other_record, user):
    # A tabela de A já ganhou a regra padrão quando a coluna de vencimento nasceu.
    rule = AlertRule.objects.filter(table=record.table).first()
    other_rule = AlertRule.objects.create(table=other_record.table, offset_days=3)

    mine = Alert.objects.create(
        record=record,
        rule=rule,
        user=user,
        trigger_date=date(2026, 8, 17),
        due_date_snapshot=date(2026, 8, 20),
    )
    theirs = Alert.objects.create(
        record=other_record,
        rule=other_rule,
        user=other_record.user,
        trigger_date=date(2026, 8, 17),
        due_date_snapshot=date(2026, 8, 20),
    )

    expected = set(AlertRule.objects.filter(user=user).values_list("id", flat=True))

    with rls.session(user.id):
        assert set(AlertRule.objects.values_list("id", flat=True)) == expected
        assert set(Alert.objects.values_list("id", flat=True)) == {mine.id}

    # Existem no banco — apenas não são alcançáveis de dentro do contexto de A.
    assert other_rule.id not in expected
    assert Alert.objects.filter(id=theirs.id).exists()


def test_without_a_user_in_context_nothing_is_visible(record, other_record):
    """
    Papel rebaixado e GUC vazia: a policy não casa com ninguém.

    É o estado de uma request anônima que chegasse a consultar dado de domínio.
    Falhar fechado (zero linhas) é o comportamento certo — falhar aberto seria
    devolver a base inteira.
    """
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(f"SET LOCAL ROLE {rls.RUNTIME_ROLE}")
        try:
            assert Record.objects.count() == 0
            assert Table.objects.count() == 0
            assert Column.objects.count() == 0
        finally:
            rls.leave()


# ---------------------------------------------------------------- escrita


def test_writing_a_row_for_another_user_is_refused(user, other_user):
    """
    A policy tem WITH CHECK, não só USING.

    Sem WITH CHECK o isolamento seria só de leitura: daria para INSERIR uma linha
    em nome de outra conta — e depois não conseguir vê-la, o que é pior do que
    recusar na hora.
    """
    with pytest.raises(Error) as excinfo, rls.session(user.id):
        Table.objects.create(user=other_user, name="Tabela plantada")

    assert "row-level security" in str(excinfo.value).lower()


def test_updating_someone_elses_row_touches_nothing(record, other_record, user):
    with rls.session(user.id):
        affected = Record.objects.filter(id=other_record.id).update(position=99)

    assert affected == 0
    other_record.refresh_from_db()
    assert other_record.position is None


def test_deleting_someone_elses_row_touches_nothing(record, other_record, user):
    with rls.session(user.id):
        Record.objects.filter(id=other_record.id).delete()

    assert Record.objects.filter(id=other_record.id).exists()


# ---------------------------------------------------------------- integração


def test_authenticated_requests_enter_the_rls_context(auth_client, table, user, monkeypatch):
    """
    Liga as duas pontas: a policy existe (testes acima) e a API passa por ela.

    Sem esta verificação, um dia alguém troca `DEFAULT_AUTHENTICATION_CLASSES`
    de volta para as classes do DRF, todo o resto continua verde, e o segundo
    isolamento some sem ninguém notar.
    """
    entered = []
    original = rls.enter

    def spy(user_id):
        entered.append(user_id)
        return original(user_id)

    monkeypatch.setattr(rls, "enter", spy)

    response = auth_client.get(reverse("tables:table-list"))

    assert response.status_code == 200
    assert entered == [user.id]


def test_the_connection_is_not_left_downgraded_after_a_request(auth_client, table):
    """
    O middleware é o que garante isto — e é o que impede que uma asserção de
    teste feita DEPOIS de um `client.get()` continue filtrada por RLS.
    """
    auth_client.get(reverse("tables:table-list"))

    with connection.cursor() as cursor:
        cursor.execute("SELECT current_user, current_setting('app.user_id', true)")
        role, guc = cursor.fetchone()

    assert role != rls.RUNTIME_ROLE
    assert not guc
