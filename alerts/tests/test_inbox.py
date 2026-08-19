from datetime import timedelta

import pytest
from django.urls import reverse

from alerts.models import Alert, AlertChannel, AlertRule, AlertStatus
from alerts.services import generate_for_user
from tables.models import Column, ColumnType, Table

from .conftest import TODAY, add_record

pytestmark = pytest.mark.django_db

INBOX = reverse("alerts:alert-list")


def detail(alert_id):
    return reverse("alerts:alert-detail", args=[alert_id])


def rules_url(table_id):
    return reverse("alerts:alert-rule-list", args=[table_id])


@pytest.fixture
def alert(user, make_record, default_rule):
    make_record(TODAY + timedelta(days=1))
    generate_for_user(user, TODAY)
    return Alert.objects.get()


# ---------------------------------------------------------------- inbox


def test_inbox_lists_the_users_alerts(auth_client, alert):
    response = auth_client.get(INBOX)

    assert response.status_code == 200
    assert [row["id"] for row in response.data["results"]] == [str(alert.id)]


def test_inbox_requires_authentication(api_client):
    assert api_client.get(INBOX).status_code == 401


def test_marking_as_read(auth_client, alert):
    response = auth_client.post(reverse("alerts:alert-read", args=[alert.id]))

    assert response.status_code == 200
    alert.refresh_from_db()
    assert alert.status == AlertStatus.READ
    assert alert.read_at is not None


def test_dismissing(auth_client, alert):
    response = auth_client.post(reverse("alerts:alert-dismiss", args=[alert.id]))

    assert response.status_code == 200
    alert.refresh_from_db()
    assert alert.status == AlertStatus.DISMISSED


def test_filtering_by_status(auth_client, alert):
    assert len(auth_client.get(INBOX, {"status": "sent"}).data["results"]) == 1
    assert len(auth_client.get(INBOX, {"status": "read"}).data["results"]) == 0


def test_alerts_cannot_be_created_through_the_api(auth_client):
    """Alertas nascem do job. Um POST daria ao cliente controle sobre o disparo."""
    assert auth_client.post(INBOX, {}, format="json").status_code == 405


# ---------------------------------------------------------------- RS05


def test_the_payload_never_carries_the_record_data(auth_client, alert):
    row = auth_client.get(INBOX).data["results"][0]

    assert "data" not in row
    assert set(row) == {
        "id", "table_id", "table_name", "record_id", "label", "trigger_date",
        "due_date", "status", "is_stale", "notified_at", "read_at", "created_at",
    }


def test_the_label_skips_sensitive_columns(auth_client, user, alert_table, default_rule):
    """
    RS05 — uma notificação aparece em lista, vira e-mail e acaba em log. É a
    superfície mais exposta do sistema; coluna sensível não entra.
    """
    add_record(alert_table, TODAY, cliente="Empresa Visível", cpf="123.456.789-00")
    generate_for_user(user, TODAY)

    body = str(auth_client.get(INBOX).data)

    assert "Empresa Visível" in body
    assert "123.456.789-00" not in body


def test_the_label_falls_back_when_every_usable_column_is_sensitive(
    auth_client, user
):
    table = Table.objects.create(user=user, name="Sigilosos", alert_lead_days=0)
    Column.objects.create(
        table=table, name="Segredo", type=ColumnType.TEXT, position=0, is_sensitive=True
    )
    Column.objects.create(table=table, name="Vence", type=ColumnType.DUE_DATE, position=1)
    record = table.records.create(
        user=user, data={"segredo": "não vaze", "vence": TODAY.isoformat()}
    )
    generate_for_user(user, TODAY)

    body = str(auth_client.get(INBOX).data)

    assert "não vaze" not in body
    assert str(record.id)[:8] in body


def test_marking_sensitive_later_also_protects_old_alerts(
    auth_client, user, alert_table, default_rule
):
    """
    O rótulo é montado na leitura, não gravado no alerta.

    Se fosse gravado, marcar a coluna como sensível depois não protegeria nada
    do que já tinha sido emitido.
    """
    add_record(alert_table, TODAY, cliente="Nome Exposto")
    generate_for_user(user, TODAY)
    assert "Nome Exposto" in str(auth_client.get(INBOX).data)

    cliente = alert_table.columns.get(key="cliente")
    cliente.is_sensitive = True
    cliente.save(update_fields=["is_sensitive"])

    assert "Nome Exposto" not in str(auth_client.get(INBOX).data)


# ---------------------------------------------------------------- RS01


def test_cannot_see_another_users_alerts(other_client, alert):
    assert other_client.get(INBOX).data["results"] == []
    assert other_client.get(detail(alert.id)).status_code == 404


def test_cannot_read_another_users_alert(other_client, alert):
    response = other_client.post(reverse("alerts:alert-read", args=[alert.id]))

    assert response.status_code == 404
    alert.refresh_from_db()
    assert alert.status == AlertStatus.SENT


# ---------------------------------------------------------------- regras


def test_listing_rules_of_a_table(auth_client, alert_table, default_rule):
    response = auth_client.get(rules_url(alert_table.id))

    assert response.status_code == 200
    assert [r["offset_days"] for r in response.data["results"]] == [3]


def test_creating_a_second_rule(auth_client, alert_table, default_rule):
    response = auth_client.post(
        rules_url(alert_table.id), {"offset_days": 0}, format="json"
    )

    assert response.status_code == 201
    assert alert_table.alert_rules.count() == 2


def test_duplicate_rule_is_rejected_with_400(auth_client, alert_table, default_rule):
    response = auth_client.post(
        rules_url(alert_table.id),
        {"offset_days": default_rule.offset_days, "channel": "in_app"},
        format="json",
    )

    assert response.status_code == 400


def test_offset_out_of_range_is_rejected(auth_client, alert_table):
    response = auth_client.post(
        rules_url(alert_table.id), {"offset_days": 400}, format="json"
    )

    assert response.status_code == 400


def test_cannot_manage_rules_of_another_users_table(auth_client, other_user):
    foreign = Table.objects.create(user=other_user, name="Alheia")

    assert auth_client.get(rules_url(foreign.id)).status_code == 404
    assert auth_client.post(
        rules_url(foreign.id), {"offset_days": 1}, format="json"
    ).status_code == 404


def test_deleting_a_rule_removes_its_alerts(auth_client, alert_table, default_rule, alert):
    url = reverse("alerts:alert-rule-detail", args=[alert_table.id, default_rule.id])

    assert auth_client.delete(url).status_code == 204
    assert not Alert.objects.filter(id=alert.id).exists()
