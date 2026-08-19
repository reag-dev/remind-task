from datetime import timedelta

import pytest
from freezegun import freeze_time

from alerts.models import Alert, AlertChannel, AlertRule, AlertStatus
from alerts.services import LOOKBACK_DAYS, generate_for_user
from alerts.tasks import scan_due_records
from tables.models import Column, ColumnType, Table

from .conftest import TODAY, add_record

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------- regra padrão


def test_a_due_date_column_creates_the_default_rule(alert_table):
    rule = alert_table.alert_rules.get()

    assert rule.offset_days == alert_table.alert_lead_days
    assert rule.channel == AlertChannel.IN_APP
    assert rule.user_id == alert_table.user_id


def test_a_table_without_due_date_column_gets_no_rule(user):
    table = Table.objects.create(user=user, name="Sem prazo")
    Column.objects.create(table=table, name="Nota", type=ColumnType.TEXT, position=0)

    assert not table.alert_rules.exists()


# ---------------------------------------------------------------- disparo


def test_alert_fires_when_the_due_date_enters_the_window(user, make_record, default_rule):
    """Regra de 3 dias: um vencimento a 3 dias entra, um a 4 dias ainda não."""
    make_record(TODAY + timedelta(days=3))
    make_record(TODAY + timedelta(days=4))

    generate_for_user(user, TODAY)

    assert Alert.objects.count() == 1
    assert Alert.objects.get().due_date_snapshot == TODAY + timedelta(days=3)


def test_an_overdue_record_still_alerts(user, make_record, default_rule):
    make_record(TODAY - timedelta(days=2))

    generate_for_user(user, TODAY)

    assert Alert.objects.count() == 1


def test_records_older_than_the_lookback_window_are_ignored(user, make_record, default_rule):
    """
    Sem a janela, cada execução varreria o histórico inteiro — 96 vezes por dia,
    para redescobrir alertas que já existem.
    """
    make_record(TODAY - timedelta(days=LOOKBACK_DAYS + 1))

    assert generate_for_user(user, TODAY) == 0


def test_a_record_without_due_date_never_alerts(user, make_record, default_rule):
    make_record(None)

    assert generate_for_user(user, TODAY) == 0


def test_an_inactive_rule_does_not_fire(user, make_record, default_rule):
    default_rule.is_active = False
    default_rule.save(update_fields=["is_active"])
    make_record(TODAY)

    assert generate_for_user(user, TODAY) == 0


def test_a_negative_offset_alerts_after_the_due_date(user, alert_table, make_record):
    """offset -2 = cobrar 2 dias DEPOIS do vencimento."""
    alert_table.alert_rules.all().delete()
    AlertRule.objects.create(table=alert_table, offset_days=-2, channel=AlertChannel.IN_APP)

    make_record(TODAY - timedelta(days=2))   # venceu há 2 dias: dispara hoje
    make_record(TODAY - timedelta(days=1))   # venceu ontem: ainda não

    generate_for_user(user, TODAY)

    assert Alert.objects.count() == 1
    assert Alert.objects.get().due_date_snapshot == TODAY - timedelta(days=2)


def test_in_app_alerts_are_delivered_immediately(user, make_record, default_rule):
    make_record(TODAY)

    generate_for_user(user, TODAY)

    alert = Alert.objects.get()
    assert alert.status == AlertStatus.SENT
    assert alert.notified_at is not None


def test_other_channels_start_pending(user, alert_table, make_record):
    alert_table.alert_rules.all().delete()
    AlertRule.objects.create(table=alert_table, offset_days=0, channel=AlertChannel.EMAIL)
    make_record(TODAY)

    generate_for_user(user, TODAY)

    alert = Alert.objects.get()
    assert alert.status == AlertStatus.PENDING
    assert alert.notified_at is None


# ---------------------------------------------------------------- vencimento mudou


def test_changing_the_due_date_drops_the_stale_alert(user, make_record, default_rule):
    """
    O aviso "vence em 20/08" vira informação errada quando o contrato é adiado.
    """
    record = make_record(TODAY + timedelta(days=1))
    generate_for_user(user, TODAY)
    assert Alert.objects.count() == 1

    record.data["vence"] = (TODAY + timedelta(days=200)).isoformat()
    record.save()

    assert Alert.objects.count() == 0


def test_the_regenerated_alert_uses_the_new_date(user, make_record, default_rule):
    record = make_record(TODAY + timedelta(days=1))
    generate_for_user(user, TODAY)

    novo = TODAY + timedelta(days=2)
    record.data["vence"] = novo.isoformat()
    record.save()
    generate_for_user(user, TODAY)

    alert = Alert.objects.get()
    assert alert.due_date_snapshot == novo
    assert alert.trigger_date == novo - timedelta(days=default_rule.offset_days)


def test_history_survives_a_due_date_change(user, make_record, default_rule):
    """Lido e descartado são registro do que aconteceu — não se apagam."""
    record = make_record(TODAY + timedelta(days=1))
    generate_for_user(user, TODAY)
    Alert.objects.update(status=AlertStatus.READ)

    record.data["vence"] = (TODAY + timedelta(days=300)).isoformat()
    record.save()

    assert Alert.objects.count() == 1
    assert Alert.objects.get().is_stale is True


# ---------------------------------------------------------------- fuso horário


def test_the_task_uses_each_users_own_today(authenticate, user, other_user):
    """
    Às 02:00 UTC é dia 20 em Tóquio e ainda dia 19 em São Paulo.

    Com regra de antecedência 0, um vencimento em 20/08 dispara para quem está em
    Tóquio e ainda não para quem está em São Paulo. Uma varredura global usando a
    data do servidor daria a mesma resposta para os dois.
    """
    user.timezone = "America/Sao_Paulo"
    user.save(update_fields=["timezone"])
    other_user.timezone = "Asia/Tokyo"
    other_user.save(update_fields=["timezone"])

    for account in (user, other_user):
        table = Table.objects.create(user=account, name="Contratos", alert_lead_days=0)
        Column.objects.create(table=table, name="Vence", type=ColumnType.DUE_DATE, position=0)
        add_record(table, TODAY + timedelta(days=1), cliente=None, cpf=None)

    with freeze_time("2026-08-20T02:00:00Z"):
        scan_due_records()

    assert Alert.objects.filter(user=other_user).count() == 1   # Tóquio: já é dia 20
    assert Alert.objects.filter(user=user).count() == 0         # São Paulo: ainda dia 19


def test_the_task_isolates_users(user, other_user, make_record, default_rule):
    make_record(TODAY)

    with freeze_time("2026-08-19T12:00:00Z"):
        created = scan_due_records()

    assert created == 1
    assert Alert.objects.filter(user=other_user).count() == 0


def test_the_task_skips_users_without_active_rules(user, make_record, default_rule):
    default_rule.delete()
    make_record(TODAY)

    with freeze_time("2026-08-19T12:00:00Z"):
        assert scan_due_records() == 0
