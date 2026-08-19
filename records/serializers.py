from rest_framework import serializers

from core.dates import user_today
from records.models import Record
from records.status import DueStatus, due_status_for
from records.validators import validate_record_data


class RecordSerializer(serializers.ModelSerializer):
    due_status = serializers.SerializerMethodField(
        help_text=f"Um de: {', '.join(DueStatus.values)}"
    )
    days_until_due = serializers.SerializerMethodField(
        help_text="Negativo quando já venceu; null quando não há vencimento."
    )

    class Meta:
        model = Record
        fields = (
            "id",
            "data",
            "due_date",
            "due_status",
            "days_until_due",
            "position",
            "created_at",
            "updated_at",
        )
        # `due_date` é derivado de data[<coluna de vencimento>] no save(); expor
        # para escrita abriria caminho para ele divergir do JSONB.
        read_only_fields = ("id", "due_date", "created_at", "updated_at")

    # O status é calculado em Python na serialização, e em SQL na queryset
    # (que é o que permite filtrar e ordenar por ele). As duas implementações
    # são conferidas por test_sql_and_python_agree_on_every_status.
    def _today(self):
        if "today" not in self.context:
            self.context["today"] = user_today(self.context["request"].user)
        return self.context["today"]

    def get_due_status(self, obj) -> str:
        return due_status_for(
            obj.due_date, self._today(), obj.table.alert_lead_days
        )

    def get_days_until_due(self, obj) -> int | None:
        if obj.due_date is None:
            return None
        return (obj.due_date - self._today()).days

    def validate_data(self, value):
        columns = self.context["columns"]

        # PATCH manda só o delta, mas a validação precisa do registro inteiro:
        # `is_required` só pode ser conferido olhando o estado final. Um PATCH
        # que apaga um campo obrigatório tem que falhar, e olhando o delta
        # isolado ele passaria.
        if self.instance is not None and self.partial:
            value = {**(self.instance.data or {}), **value}

        return validate_record_data(value, columns)

    def create(self, validated_data):
        # O dono nunca vem do corpo: o save() do model o copia da tabela-mãe.
        return Record.objects.create(table=self.context["table"], **validated_data)
