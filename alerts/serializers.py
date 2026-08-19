from rest_framework import serializers

from alerts.models import Alert, AlertRule
from alerts.services import record_label


class AlertRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlertRule
        fields = ("id", "offset_days", "channel", "is_active", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

    def validate(self, attrs):
        table = self.context["table"]
        offset_days = attrs.get(
            "offset_days", getattr(self.instance, "offset_days", None)
        )
        channel = attrs.get("channel", getattr(self.instance, "channel", None))

        # O banco garante (alert_rules_unique); aqui é só para devolver 400 com
        # mensagem em vez de deixar o IntegrityError virar 500.
        duplicates = AlertRule.objects.filter(
            table=table, offset_days=offset_days, channel=channel
        )
        if self.instance is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError(
                "Já existe uma regra com essa antecedência e canal nesta tabela."
            )
        return attrs

    def create(self, validated_data):
        return AlertRule.objects.create(table=self.context["table"], **validated_data)


class AlertSerializer(serializers.ModelSerializer):
    """
    Payload da notificação.

    RS05 — carrega o mínimo: nome da tabela, vencimento e um rótulo curto do
    registro. NUNCA o `data` completo, e nunca o valor de uma coluna marcada
    como sensível. Uma notificação é a superfície mais exposta do sistema:
    aparece em lista, vira e-mail e acaba em log.
    """

    table_name = serializers.CharField(source="record.table.name", read_only=True)
    table_id = serializers.UUIDField(source="record.table_id", read_only=True)
    record_id = serializers.UUIDField(read_only=True)
    due_date = serializers.DateField(source="due_date_snapshot", read_only=True)
    label = serializers.SerializerMethodField()
    is_stale = serializers.BooleanField(read_only=True)

    class Meta:
        model = Alert
        fields = (
            "id",
            "table_id",
            "table_name",
            "record_id",
            "label",
            "trigger_date",
            "due_date",
            "status",
            "is_stale",
            "notified_at",
            "read_at",
            "created_at",
        )
        read_only_fields = fields

    def get_label(self, alert) -> str:
        return record_label(alert.record, alert.record.table.columns.all())
