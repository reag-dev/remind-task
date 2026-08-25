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


def test_the_owner_is_not_subject_to_the_policies(record):
    """
    `FORCE ROW LEVEL SECURITY` fica DESLIGADO — decisão da migration 0002.

    Com FORCE, as policies valem também para o dono da tabela. Em produção, onde
    o dono não é superusuário, isso apagaria o Django Admin (lista zero linhas),
    quebraria a exclusão de usuário na cascata e faria data migrations rodarem
    contra zero linhas reportando sucesso — três falhas silenciosas.

    O isolamento do runtime não depende disso: `remind_app` não é dono, então as
    policies valem para ele de qualquer jeito. É o que o primeiro teste deste
    arquivo confere.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT relname, relrowsecurity, relforcerowsecurity
            FROM pg_class
            WHERE relnamespace = 'public'::regnamespace
              AND relname IN ('tables', 'columns', 'records', 'alert_rules',
                              'alerts', 'users')
            ORDER BY relname
            """
        )
        estado = cursor.fetchall()

    # Seis: as cinco de domínio da migration 0001 e `users`, que entrou na 0003
    # quando passou a existir um endpoint capaz de apagar conta.
    assert len(estado) == 6
    for relname, enabled, forced in estado:
        assert enabled, f"{relname} está sem RLS"
        assert not forced, f"{relname} está com FORCE — ver migration 0002"


# ------------------------------------------------------------ users (Phase 11)


def test_users_table_is_isolated_too(user, other_user):
    """
    A policy que faltava, e que só passou a importar quando surgiu o DELETE.

    Enquanto nenhum endpoint apagava conta, a ausência era inofensiva: o
    `MeView` opera sobre `request.user`, que vem do token. `DELETE
    /api/auth/me/` mudou isso — é a operação mais destrutiva do sistema, e sem
    policy seria a única sem a segunda barreira.
    """
    User = type(user)

    with rls.session(user.id):
        visible = set(User.objects.values_list("id", flat=True))

    assert visible == {user.id}
    # Existe no banco; apenas não é alcançável de dentro do contexto de A.
    assert User.objects.filter(pk=other_user.pk).exists()


def test_deleting_someone_elses_account_touches_nothing(user, other_user):
    """
    A propriedade que a policy compra, dita na forma do ataque que ela impede.

    Um bug de queryset que resolvesse o usuário por id vindo do corpo — em vez
    de `request.user` — encontraria aqui a segunda barreira.
    """
    User = type(user)

    with rls.session(user.id):
        User.objects.filter(pk=other_user.pk).delete()

    assert User.objects.filter(pk=other_user.pk).exists()


def test_the_policy_on_users_does_not_break_login(api_client, user, password):
    """
    A pergunta que fez esta policy parecer inviável no plano.

    Login consulta `users` por e-mail **antes** de existir usuário autenticado —
    se ele rodasse sob a policy, a GUC estaria vazia e a busca não acharia
    ninguém: ninguém mais entraria no sistema.

    Não é o caso, e o motivo é estrutural: o contexto de RLS é aberto nas classes
    de autenticação do DRF (`core/rls.py`), e requisições pré-autenticação nunca
    passam por lá. O login roda como dono, e o dono não está sujeito às policies
    (sem FORCE, ver a migration 0002).
    """
    resposta = api_client.post(
        reverse("accounts:login"), {"email": user.email, "password": password}, format="json"
    )

    assert resposta.status_code == 200
    assert resposta.json()["user"]["email"] == user.email


def test_the_alert_job_can_still_join_the_user_row(record, user):
    """
    O caminho que a policy poderia ter quebrado sem ninguém notar até o cron.

    `alerts.tasks.send_pending_email` roda dentro de `rls.session(user_id)` e faz
    `select_related("user")` — um JOIN em `users`. A linha juntada é a do próprio
    dono do alerta, então a policy permite. Se um dia alguém apertar a regra e
    esquecer disso, os e-mails param silenciosamente.
    """
    rule = AlertRule.objects.filter(table=record.table).first()
    alerta = Alert.objects.create(
        record=record,
        rule=rule,
        user=user,
        trigger_date=date(2026, 8, 17),
        due_date_snapshot=date(2026, 8, 20),
    )

    with rls.session(user.id):
        carregado = Alert.objects.select_related("user").get(pk=alerta.pk)
        assert carregado.user.email == user.email
