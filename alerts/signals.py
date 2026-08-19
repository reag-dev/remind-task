from django.db.models.signals import post_save
from django.dispatch import receiver

from alerts.models import Alert, AlertStatus
from alerts.services import ensure_default_rule
from records.models import Record
from tables.models import Column, ColumnType


@receiver(post_save, sender=Column, dispatch_uid="alerts.default_rule")
def create_default_rule(sender, instance: Column, created, **kwargs):
    """
    Uma tabela ganha regra de alerta quando ganha coluna de vencimento.

    O gancho é a coluna, não a tabela: uma tabela nasce vazia e só vira
    "controlável por prazo" quando a coluna `due_date` aparece. Como sinal — e
    não dentro da view — a regra também é criada por seed, script ou admin.
    """
    if not created or instance.type != ColumnType.DUE_DATE:
        return
    ensure_default_rule(instance.table)


@receiver(post_save, sender=Record, dispatch_uid="alerts.drop_stale")
def drop_stale_alerts(sender, instance: Record, created, **kwargs):
    """
    Remove alertas ainda acionáveis que descrevem um vencimento antigo.

    Se o usuário adia um contrato de agosto para janeiro, o aviso "vence em
    20/08" no inbox passa a ser informação errada. Os que já foram lidos ou
    descartados ficam: são histórico do que de fato aconteceu.

    Declarativo em vez de rastrear a mudança: qualquer alerta acionável cujo
    `due_date_snapshot` discorde do vencimento atual está obsoleto, não importa
    como chegou lá. O job regenera com o `trigger_date` novo.
    """
    if created:
        return

    Alert.objects.filter(
        record=instance, status__in=AlertStatus.actionable()
    ).exclude(due_date_snapshot=instance.due_date).delete()
