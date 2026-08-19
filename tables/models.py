from django.conf import settings
from django.core.validators import MaxValueValidator
from django.db import models
from django.db.models import Deferrable, Q
from django.utils.text import slugify

from core.models import TimeStampedUUIDModel

KEY_MAX_LENGTH = 64
KEY_FALLBACK = "coluna"


class ColumnType(models.TextChoices):
    """
    Tipos de coluna (RF05).

    Guardado como varchar + CHECK, não como ENUM nativo do Postgres: acrescentar
    um tipo novo aqui é uma migration de constraint, enquanto num ENUM nativo
    seria `ALTER TYPE ... ADD VALUE`, que não roda dentro de transação e não tem
    reversão. A lista tende a crescer (RF05 prevê evolução), então varchar ganha.
    """

    TEXT = "text", "Texto"
    NUMBER = "number", "Número"
    DATE = "date", "Data"
    DATETIME = "datetime", "Data e hora"
    BOOLEAN = "boolean", "Booleano"
    EMAIL = "email", "E-mail"
    SELECT = "select", "Lista de opções"
    DUE_DATE = "due_date", "Data de vencimento"


class Table(TimeStampedUUIDModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tables",
        verbose_name="dono",
    )
    name = models.CharField("nome", max_length=120)
    description = models.TextField("descrição", blank=True, default="")

    # Limiar de "próximo do vencimento" (RF10) e antecedência da AlertRule
    # padrão criada na Phase 5.
    alert_lead_days = models.PositiveSmallIntegerField(
        "dias de antecedência do alerta",
        default=3,
        validators=[MaxValueValidator(365)],
    )

    class Meta:
        db_table = "tables"
        ordering = ["-created_at"]
        verbose_name = "tabela"
        verbose_name_plural = "tabelas"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "name"], name="tables_unique_name_per_user"
            ),
            models.CheckConstraint(
                condition=Q(alert_lead_days__lte=365),
                name="tables_alert_lead_days_range",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="tables_user_created_idx"),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def due_date_column(self):
        """A coluna de vencimento da tabela, se existir. No máximo uma (RF06)."""
        return self.columns.filter(type=ColumnType.DUE_DATE).first()


class Column(TimeStampedUUIDModel):
    table = models.ForeignKey(
        Table, on_delete=models.CASCADE, related_name="columns", verbose_name="tabela"
    )

    # Chave usada dentro de records.data. IMUTÁVEL depois da criação: é o que
    # permite renomear a coluna (RF05) sem reescrever nenhum registro.
    key = models.SlugField("chave", max_length=KEY_MAX_LENGTH, editable=False)

    name = models.CharField("rótulo", max_length=80)
    type = models.CharField("tipo", max_length=16, choices=ColumnType.choices)
    position = models.PositiveSmallIntegerField("posição")
    is_required = models.BooleanField("obrigatória", default=False)

    # RS05: marca a coluna para redação em logs, notificações e payload de alerta.
    is_sensitive = models.BooleanField("sensível", default=False)

    options = models.JSONField("opções", default=list, blank=True)

    class Meta:
        db_table = "columns"
        ordering = ["position"]
        verbose_name = "coluna"
        verbose_name_plural = "colunas"
        constraints = [
            models.UniqueConstraint(
                fields=["table", "key"], name="columns_unique_key"
            ),
            # DEFERRED: durante um reorder as posições passam por estados
            # temporariamente duplicados. A checagem no COMMIT deixa a permutação
            # acontecer numa transação só, sem posições negativas de rascunho.
            models.UniqueConstraint(
                fields=["table", "position"],
                name="columns_unique_position",
                deferrable=Deferrable.DEFERRED,
            ),
            # RF06: no máximo uma coluna de vencimento por tabela.
            models.UniqueConstraint(
                fields=["table"],
                condition=Q(type=ColumnType.DUE_DATE),
                name="columns_one_due_date_per_table",
            ),
            models.CheckConstraint(
                condition=Q(type__in=ColumnType.values),
                name="columns_type_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.table.name}.{self.key}"

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = self._build_key()
        super().save(*args, **kwargs)

    def _build_key(self) -> str:
        """
        Slug estável derivado do rótulo, único dentro da tabela.

        Nomes que não produzem slug ("***", "###") caem no fallback em vez de
        gerar chave vazia — string vazia colidiria com qualquer outra igual.
        """
        base = slugify(self.name).replace("-", "_")[:KEY_MAX_LENGTH] or KEY_FALLBACK
        candidate = base
        taken = set(
            Column.objects.filter(table_id=self.table_id)
            .exclude(pk=self.pk)
            .values_list("key", flat=True)
        )

        suffix = 2
        while candidate in taken:
            tail = f"_{suffix}"
            candidate = f"{base[: KEY_MAX_LENGTH - len(tail)]}{tail}"
            suffix += 1

        return candidate
