"""
Geração de alertas (RF12) e montagem do payload seguro (RS05).
"""

from datetime import date, timedelta

from django.utils import timezone

from alerts.models import Alert, AlertChannel, AlertRule, AlertStatus
from records.models import Record
from tables.models import ColumnType

# Quanto tempo para trás o job olha. Sem esta janela, cada execução varreria o
# histórico inteiro para redescobrir alertas que já existem — 96 vezes por dia.
LOOKBACK_DAYS = 30

LABEL_MAX_LENGTH = 80


def ensure_default_rule(table) -> AlertRule | None:
    """
    Garante a regra padrão de uma tabela que tenha coluna de vencimento.

    Idempotente: chamada a cada save de coluna, cria no máximo uma.
    """
    if table.due_date_column is None:
        return None

    rule, _ = AlertRule.objects.get_or_create(
        table=table,
        offset_days=table.alert_lead_days,
        channel=AlertChannel.IN_APP,
        defaults={"user_id": table.user_id},
    )
    return rule


def record_label(record, columns) -> str:
    """
    Rótulo curto do registro para aparecer na notificação.

    RS05: pula colunas marcadas como sensíveis. Calculado na leitura, não gravado
    no alerta — assim marcar uma coluna como sensível depois também protege os
    alertas já emitidos.
    """
    for column in columns:
        if column.is_sensitive or column.type == ColumnType.DUE_DATE:
            continue
        value = (record.data or {}).get(column.key)
        if value not in (None, ""):
            return str(value)[:LABEL_MAX_LENGTH]

    # Nenhuma coluna utilizável: o id abreviado identifica sem revelar conteúdo.
    return f"Registro {str(record.id)[:8]}"


def generate_for_user(user, today: date) -> int:
    """
    Cria os alertas devidos de um usuário. Devolve quantos foram criados.

    `today` vem de fora porque depende do fuso do usuário — por isso o job
    percorre usuário a usuário em vez de fazer uma varredura global.
    """
    rules = list(
        AlertRule.objects.filter(user=user, is_active=True).select_related("table")
    )
    if not rules:
        return 0

    window_start = today - timedelta(days=LOOKBACK_DAYS)
    now = timezone.now()
    pending: list[Alert] = []

    for rule in rules:
        # trigger_date = due_date - offset  ≤  hoje   ⟺   due_date ≤ hoje + offset
        cutoff = today + timedelta(days=rule.offset_days)

        due_records = Record.objects.filter(
            table_id=rule.table_id,
            due_date__isnull=False,
            due_date__gte=window_start,
            due_date__lte=cutoff,
        ).values_list("id", "due_date")

        # Pré-filtro do que já existe. A constraint sozinha bastaria para a
        # correção, mas sem isto cada execução reenviaria todas as linhas da
        # janela para o Postgres só para ele recusar — a cada 15 minutos.
        already = set(
            Alert.objects.filter(rule=rule, trigger_date__gte=window_start).values_list(
                "record_id", "trigger_date"
            )
        )

        delivered_immediately = rule.channel == AlertChannel.IN_APP

        for record_id, due_date in due_records.iterator(chunk_size=1000):
            trigger_date = due_date - timedelta(days=rule.offset_days)
            if (record_id, trigger_date) in already:
                continue

            pending.append(
                Alert(
                    record_id=record_id,
                    rule=rule,
                    user_id=rule.user_id,
                    trigger_date=trigger_date,
                    due_date_snapshot=due_date,
                    # in_app "entrega" no ato: o alerta já fica visível no inbox.
                    # Outros canais nascem pendentes até o envio confirmar.
                    status=AlertStatus.SENT if delivered_immediately else AlertStatus.PENDING,
                    notified_at=now if delivered_immediately else None,
                )
            )

    if not pending:
        return 0

    # ignore_conflicts continua ligado: é a rede contra dois workers rodando a
    # mesma janela ao mesmo tempo, que o pré-filtro sozinho não cobre.
    Alert.objects.bulk_create(pending, ignore_conflicts=True, batch_size=500)
    return len(pending)
