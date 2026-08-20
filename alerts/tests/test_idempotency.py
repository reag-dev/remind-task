"""
RF12 exige explicitamente evitar envio duplicado. Estes testes atacam esse ponto
por três lados: repetição do job, escrita concorrente e a constraint do banco.
"""

from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction

from alerts.models import Alert, AlertStatus
from alerts.services import generate_for_user

from .conftest import TODAY

pytestmark = pytest.mark.django_db


def test_running_the_scan_three_times_creates_one_alert(user, make_record, default_rule):
    make_record(TODAY + timedelta(days=1))

    for _ in range(3):
        generate_for_user(user, TODAY)

    assert Alert.objects.count() == 1


def test_the_second_run_reports_zero_created(user, make_record, default_rule):
    make_record(TODAY + timedelta(days=1))

    first = generate_for_user(user, TODAY)
    second = generate_for_user(user, TODAY)

    assert first == 1
    assert second == 0


def test_the_database_rejects_a_duplicate_even_bypassing_the_service(
    user, make_record, default_rule
):
    """
    A garantia real é a constraint, não o pré-filtro do serviço.

    Sem ela, dois workers varrendo a mesma janela ao mesmo tempo leriam ambos
    "ainda não existe" e ambos inseririam.
    """
    record = make_record(TODAY + timedelta(days=1))
    generate_for_user(user, TODAY)
    existing = Alert.objects.get()

    with pytest.raises(IntegrityError), transaction.atomic():
        Alert.objects.create(
            record=record,
            rule=default_rule,
            user=user,
            trigger_date=existing.trigger_date,
            due_date_snapshot=existing.due_date_snapshot,
        )


def test_an_alert_already_read_is_not_recreated(user, make_record, default_rule):
    """Reagendar o alerta já lido faria a notificação reaparecer sozinha."""
    make_record(TODAY + timedelta(days=1))
    generate_for_user(user, TODAY)

    Alert.objects.update(status=AlertStatus.READ)
    generate_for_user(user, TODAY)

    assert Alert.objects.count() == 1
    assert Alert.objects.get().status == AlertStatus.READ


def test_a_dismissed_alert_is_not_recreated(user, make_record, default_rule):
    make_record(TODAY + timedelta(days=1))
    generate_for_user(user, TODAY)
    Alert.objects.update(status=AlertStatus.DISMISSED)

    generate_for_user(user, TODAY)

    assert Alert.objects.count() == 1


def test_running_on_consecutive_days_does_not_duplicate(user, make_record, default_rule):
    """
    `trigger_date` é derivado do vencimento, não do dia da execução.

    Se dependesse de "hoje", cada dia produziria um alerta novo para o mesmo
    vencimento e o inbox encheria sozinho.
    """
    make_record(TODAY + timedelta(days=1))

    for offset in range(5):
        generate_for_user(user, TODAY + timedelta(days=offset))

    assert Alert.objects.count() == 1


def test_two_rules_produce_two_distinct_alerts(user, make_record, alert_table, default_rule):
    """Antecedências diferentes são avisos diferentes — não é duplicata."""
    from alerts.models import AlertChannel, AlertRule

    AlertRule.objects.create(table=alert_table, offset_days=0, channel=AlertChannel.IN_APP)
    make_record(TODAY)

    generate_for_user(user, TODAY)

    assert Alert.objects.count() == 2
    assert Alert.objects.values("rule").distinct().count() == 2
