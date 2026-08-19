from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from core.models import TimeStampedUUIDModel
from records.models import Record
from tables.models import Table

OFFSET_LIMIT = 365


class AlertChannel(models.TextChoices):
    IN_APP = "in_app", "No aplicativo"
    EMAIL = "email", "E-mail"


class AlertStatus(models.TextChoices):
    PENDING = "pending", "Pendente"
    SENT = "sent", "Enviado"
    READ = "read", "Lido"
    DISMISSED = "dismissed", "Descartado"
    FAILED = "failed", "Falhou"

    @classmethod
    def actionable(cls):
        """Ainda exigem atenção do usuário — o oposto de histórico."""
        return (cls.PENDING, cls.SENT)


class AlertRule(TimeStampedUUIDModel):
    """
    Quando avisar sobre os vencimentos de uma tabela.

    Não existia no modelo conceitual da especificação: RF12 lista "diferentes
    níveis de antecedência" como evolução, e sem uma entidade própria isso viraria
    um campo fixo por tabela, sem espaço para duas antecedências simultâneas
    (avisar 7 dias antes E no dia).
    """

    table = models.ForeignKey(
        Table, on_delete=models.CASCADE, related_name="alert_rules", verbose_name="tabela"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="alert_rules",
        verbose_name="dono",
    )

    offset_days = models.SmallIntegerField(
        "dias de antecedência",
        validators=[MinValueValidator(-OFFSET_LIMIT), MaxValueValidator(OFFSET_LIMIT)],
        help_text="3 = avisa 3 dias antes · 0 = no dia · -1 = 1 dia depois (cobrança de atraso).",
    )
    channel = models.CharField(
        "canal", max_length=16, choices=AlertChannel.choices, default=AlertChannel.IN_APP
    )
    is_active = models.BooleanField("ativa", default=True)

    class Meta:
        db_table = "alert_rules"
        ordering = ["-offset_days"]
        verbose_name = "regra de alerta"
        verbose_name_plural = "regras de alerta"
        constraints = [
            models.UniqueConstraint(
                fields=["table", "offset_days", "channel"], name="alert_rules_unique"
            ),
            models.CheckConstraint(
                condition=Q(offset_days__gte=-OFFSET_LIMIT, offset_days__lte=OFFSET_LIMIT),
                name="alert_rules_offset_range",
            ),
            models.CheckConstraint(
                condition=Q(channel__in=AlertChannel.values), name="alert_rules_channel_valid"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.table.name}: {self.offset_days:+d}d via {self.channel}"

    def save(self, *args, **kwargs):
        if not self.user_id and self.table_id:
            self.user_id = self.table.user_id
        super().save(*args, **kwargs)


class Alert(TimeStampedUUIDModel):
    """
    Um alerta disparado — a notificação em si.

    A idempotência (RF12: "evitar envio duplicado") é responsabilidade do BANCO,
    via `alerts_idempotency`. Confiar em `notified_at IS NULL` não resolve
    concorrência: dois workers leem NULL ao mesmo tempo e ambos inserem.
    """

    record = models.ForeignKey(
        Record, on_delete=models.CASCADE, related_name="alerts", verbose_name="registro"
    )
    rule = models.ForeignKey(
        AlertRule, on_delete=models.CASCADE, related_name="alerts", verbose_name="regra"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="alerts",
        verbose_name="destinatário",
    )

    trigger_date = models.DateField("data de disparo")

    # Vencimento vigente quando o alerta nasceu. Se o registro mudar de data, o
    # alerta ainda acionável passa a descrever um prazo que não existe mais —
    # comparar com o due_date atual é o que permite detectar isso.
    due_date_snapshot = models.DateField("vencimento no disparo")

    status = models.CharField(
        "situação", max_length=16, choices=AlertStatus.choices, default=AlertStatus.PENDING
    )
    notified_at = models.DateTimeField("notificado em", null=True, blank=True)
    read_at = models.DateTimeField("lido em", null=True, blank=True)

    class Meta:
        db_table = "alerts"
        ordering = ["-trigger_date", "-created_at"]
        verbose_name = "alerta"
        verbose_name_plural = "alertas"
        constraints = [
            # A chave da idempotência: mesmo registro + mesma regra + mesma data
            # de disparo só existe uma vez, aconteça o que acontecer com o job.
            models.UniqueConstraint(
                fields=["record", "rule", "trigger_date"], name="alerts_idempotency"
            ),
            models.CheckConstraint(
                condition=Q(status__in=AlertStatus.values), name="alerts_status_valid"
            ),
        ]
        indexes = [
            models.Index(
                fields=["user", "status", "-trigger_date"], name="alerts_inbox_idx"
            ),
            models.Index(
                fields=["status", "trigger_date"],
                condition=Q(status=AlertStatus.PENDING),
                name="alerts_pending_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.trigger_date} · {self.status}"

    @property
    def is_stale(self) -> bool:
        """O vencimento mudou depois que este alerta foi gerado."""
        return self.due_date_snapshot != self.record.due_date
