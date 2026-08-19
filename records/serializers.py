from rest_framework import serializers

from records.models import Record
from records.validators import validate_record_data


class RecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = Record
        fields = ("id", "data", "due_date", "position", "created_at", "updated_at")
        # `due_date` é derivado de data[<coluna de vencimento>] no save(); expor
        # para escrita abriria caminho para ele divergir do JSONB.
        # `position` só muda pelo endpoint de reorder (Phase 4).
        read_only_fields = ("id", "due_date", "position", "created_at", "updated_at")

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
