from django.db.models import Max
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from tables.models import Column, ColumnType, Table


class DueSummarySerializer(serializers.Serializer):
    """
    Forma de `TableSerializer.due_summary` — só para o schema OpenAPI.

    Sem isto, drf-spectacular não sabe o que um `SerializerMethodField` cru
    devolve e cai para `string`: o `schema.d.ts` gerado mentiria sobre o
    tipo, e o frontend tipado leria `table.due_summary.overdue` como erro de
    tipo (ou pior, sem erro nenhum se alguém tivesse tipado à mão).
    """

    overdue = serializers.IntegerField()
    due_today = serializers.IntegerField()
    due_soon = serializers.IntegerField()


class ColumnSerializer(serializers.ModelSerializer):
    class Meta:
        model = Column
        fields = (
            "id",
            "key",
            "name",
            "type",
            "position",
            "is_required",
            "is_sensitive",
            "options",
            "created_at",
            "updated_at",
        )
        # `key` é derivado do nome e imutável; `position` só muda pelo endpoint
        # de reorder, que faz a permutação inteira numa transação — deixar cada
        # PATCH mexer numa posição isolada produziria colisão.
        read_only_fields = ("id", "key", "position", "created_at", "updated_at")

    def validate_options(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Deve ser uma lista.")

        cleaned = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise serializers.ValidationError(
                    "Cada opção deve ser um texto não vazio."
                )
            cleaned.append(item.strip())

        if len(set(cleaned)) != len(cleaned):
            raise serializers.ValidationError("Há opções repetidas.")
        return cleaned

    def _table(self):
        """A tabela-mãe: do contexto na criação, da própria instância na edição."""
        if self.instance is not None:
            return self.instance.table
        return self.context.get("table")

    def validate(self, attrs):
        # `type` é imutável: mudar o tipo de uma coluna deixaria os registros já
        # gravados com valores que não passam mais na validação da Phase 3 —
        # corrupção silenciosa. Para trocar o tipo, apague e recrie a coluna.
        if (
            self.instance is not None
            and "type" in attrs
            and attrs["type"] != self.instance.type
        ):
            raise serializers.ValidationError(
                {"type": "O tipo de uma coluna não pode ser alterado. "
                         "Apague a coluna e crie outra."}
            )

        column_type = attrs.get("type") or getattr(self.instance, "type", None)

        # RF06 — no máximo uma coluna de vencimento por tabela.
        # O índice único parcial no banco é a garantia real; esta checagem existe
        # só para devolver 400 em vez de deixar o IntegrityError virar 500.
        if column_type == ColumnType.DUE_DATE:
            table = self._table()
            if table is not None:
                duplicates = table.columns.filter(type=ColumnType.DUE_DATE)
                if self.instance is not None:
                    duplicates = duplicates.exclude(pk=self.instance.pk)
                if duplicates.exists():
                    raise serializers.ValidationError(
                        {"type": "Esta tabela já tem uma coluna de vencimento."}
                    )

        options = attrs.get("options")
        if options is None and self.instance is not None:
            options = self.instance.options

        if column_type == ColumnType.SELECT:
            if not options:
                raise serializers.ValidationError(
                    {"options": "Uma coluna do tipo lista precisa de ao menos uma opção."}
                )
        elif options:
            raise serializers.ValidationError(
                {"options": f"O tipo '{column_type}' não aceita opções."}
            )

        return attrs

    def create(self, validated_data):
        table = self.context["table"]

        # Anexa no fim. A ordem só muda pelo endpoint de reorder.
        last = table.columns.aggregate(Max("position"))["position__max"]
        validated_data["position"] = 0 if last is None else last + 1

        return Column.objects.create(table=table, **validated_data)


class TableSerializer(serializers.ModelSerializer):
    columns = ColumnSerializer(many=True, read_only=True)
    due_summary = serializers.SerializerMethodField()

    class Meta:
        model = Table
        fields = (
            "id",
            "name",
            "description",
            "alert_lead_days",
            "columns",
            "due_summary",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "columns", "due_summary", "created_at", "updated_at")

    @extend_schema_field(DueSummarySerializer)
    def get_due_summary(self, obj):
        """
        `{overdue, due_today, due_soon}` — só os estados que pedem atenção.
        `on_track`/`no_due` não entram: a tela de "Suas tabelas" quer dizer o
        que precisa de ação, não o total de registros.

        Vem de `due_summary_map` no contexto (uma query para todas as tabelas
        do usuário, montada em `TableViewSet.get_serializer_context`) — nunca
        calculado aqui, que rodaria uma query por tabela.
        """
        contagens = self.context.get("due_summary_map", {}).get(obj.id, {})
        return {
            "overdue": contagens.get("overdue", 0),
            "due_today": contagens.get("due_today", 0),
            "due_soon": contagens.get("due_soon", 0),
        }

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("O nome não pode ser vazio.")

        # O banco garante a unicidade (tables_unique_name_per_user); aqui é só
        # para devolver 400 com mensagem em vez de estourar IntegrityError.
        duplicates = Table.objects.filter(user=self.context["request"].user, name=value)
        if self.instance is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError("Você já tem uma tabela com esse nome.")

        return value


class ReorderSerializer(serializers.Serializer):
    order = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
        help_text="Ids de TODAS as colunas da tabela, na ordem desejada.",
    )

    def validate_order(self, value):
        if len(set(value)) != len(value):
            raise serializers.ValidationError("Há ids repetidos.")

        current = set(self.context["table"].columns.values_list("id", flat=True))
        if set(value) != current:
            raise serializers.ValidationError(
                "A lista precisa conter exatamente as colunas desta tabela."
            )
        return value
