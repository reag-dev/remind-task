from datetime import date

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import Q
from django.db.models.expressions import RawSQL

from core.models import TimeStampedUUIDModel
from tables.models import Table


class RecordQuerySet(models.QuerySet):
    def for_user(self, user):
        return self.filter(user=user)

    def purge_column_key(self, *, table_id, key: str, was_due_date: bool) -> int:
        """
        Remove uma chave do JSONB de todos os registros da tabela.

        Chamado quando a coluna é excluída. Sem isso o `data` acumula chaves
        órfãs: elas reaparecem no CSV (RF13), incham o índice GIN e voltam a ser
        interpretadas se alguém recriar uma coluna com o mesmo slug.

        O operador `-` de jsonb não tem equivalente no ORM, daí o RawSQL.
        """
        queryset = self.filter(table_id=table_id)

        updates = {"data": RawSQL("data - %s", (key,))}
        if was_due_date:
            # A coluna promovida perdeu a origem — deixar o valor antigo faria o
            # job de alertas (RF12) disparar por um vencimento que não existe mais.
            updates["due_date"] = None

        return queryset.update(**updates)


class Record(TimeStampedUUIDModel):
    # db_index=False: o índice automático de FK seria redundante com
    # records_table_due_idx (table_id, due_date), que já atende busca por
    # table_id sozinho pelo prefixo. Dois índices para o mesmo prefixo só custam
    # escrita e espaço.
    table = models.ForeignKey(
        Table,
        on_delete=models.CASCADE,
        related_name="records",
        verbose_name="tabela",
        db_index=False,
    )

    # Desnormalizado a partir de table.user (nota 1 do modelo de dados): a policy
    # de RLS da Phase 7 dispensa subquery e o filtro por dono usa índice direto.
    # Preenchido no save() a partir da tabela-mãe, NUNCA do corpo da requisição.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="records",
        verbose_name="dono",
    )

    data = models.JSONField("valores", default=dict, blank=True)

    # Promovida de data[<key da coluna due_date>] (nota 2). Cache derivado: é o
    # que permite ao job de alertas e à ordenação (RF11) usarem índice B-tree em
    # vez de varrer e converter texto do JSONB linha a linha.
    due_date = models.DateField("vencimento", null=True, blank=True)

    position = models.IntegerField("posição manual", null=True, blank=True)

    objects = RecordQuerySet.as_manager()

    class Meta:
        db_table = "records"
        verbose_name = "registro"
        verbose_name_plural = "registros"
        # ASC coloca NULL por último no Postgres, que é exatamente a ordem do
        # RF11: vencidos → hoje → próximos → futuros → sem vencimento.
        ordering = ["due_date", "created_at"]
        indexes = [
            models.Index(fields=["table", "due_date"], name="records_table_due_idx"),
            models.Index(
                fields=["due_date"],
                condition=Q(due_date__isnull=False),
                name="records_due_scan_idx",
            ),
            GinIndex(
                fields=["data"], name="records_data_gin", opclasses=["jsonb_path_ops"]
            ),
        ]

    def __str__(self) -> str:
        return f"{self.table.name} #{str(self.id)[:8]}"

    # ------------------------------------------------------------------ save

    def derive_due_date(self) -> date | None:
        """Lê o vencimento do JSONB. O JSONB continua sendo a fonte da verdade."""
        column = self.table.due_date_column
        if column is None:
            return None

        raw = (self.data or {}).get(column.key)
        if not raw:
            return None
        if isinstance(raw, date):
            return raw
        try:
            return date.fromisoformat(str(raw))
        except ValueError:
            # O serializer já rejeita formato inválido; aqui só evitamos que uma
            # escrita direta pelo ORM derrube o save inteiro.
            return None

    def save(self, *args, **kwargs):
        if not self.user_id and self.table_id:
            self.user_id = self.table.user_id

        self.due_date = self.derive_due_date()

        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            # due_date é derivado: se `data` está sendo salvo, ele muda junto.
            kwargs["update_fields"] = set(update_fields) | {"due_date", "updated_at"}

        super().save(*args, **kwargs)
