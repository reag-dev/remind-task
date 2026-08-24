"""
Um conjunto COMPLETO de recursos para cada dono.

O `conftest.py` da raiz já entrega `user`/`other_user` e um par de tabelas soltas.
Aqui o par é completado — coluna, registro, regra e alerta dos dois lados —
porque o teste de cross-tenant precisa de um id alheio de **cada tipo** de
recurso, não só de tabela.
"""

from dataclasses import dataclass
from datetime import date

import pytest

from alerts.models import Alert, AlertRule
from records.models import Record
from tables.models import Column, ColumnType, Table

DUE = date(2026, 9, 1)
TRIGGER = date(2026, 8, 29)

SENSITIVE_VALUE = "111.222.333-44"


@dataclass(frozen=True)
class Resources:
    """Tudo o que um dono tem, para montar as URLs do teste."""

    user: object
    table: Table
    column: Column
    record: Record
    rule: AlertRule
    alert: Alert


def build_resources(owner, table_name: str) -> Resources:
    table = Table.objects.create(user=owner, name=table_name, alert_lead_days=3)

    column = Column.objects.create(
        table=table, name="Cliente", type=ColumnType.TEXT, position=0
    )
    Column.objects.create(
        table=table, name="CPF", type=ColumnType.TEXT, position=1, is_sensitive=True
    )
    # A regra padrão nasce junto com a coluna de vencimento.
    Column.objects.create(table=table, name="Vence", type=ColumnType.DUE_DATE, position=2)

    record = Record.objects.create(
        table=table,
        data={"cliente": "Empresa", "cpf": SENSITIVE_VALUE, "vence": DUE.isoformat()},
    )
    rule = table.alert_rules.get()
    alert = Alert.objects.create(
        record=record,
        rule=rule,
        user=owner,
        trigger_date=TRIGGER,
        due_date_snapshot=DUE,
    )
    return Resources(owner, table, column, record, rule, alert)


@pytest.fixture
def mine(db, user) -> Resources:
    return build_resources(user, "Contratos de A")


@pytest.fixture
def theirs(db, other_user) -> Resources:
    return build_resources(other_user, "Contratos de B")


# ------------------------------------------------- fixtures vindas de alerts

# `alert_table` (com coluna sensível) e `make_record` moram no conftest de
# `alerts/tests/`, que não alcança este diretório. Re-exportadas aqui, e não
# copiadas: uma segunda definição da mesma tabela envelheceria em silêncio — no
# dia em que a coluna sensível mudasse de nome lá, `test_email_redaction.py`
# continuaria passando medindo outra coisa.
#
# O conftest é o lugar certo para isto. Importar no próprio módulo de teste
# funciona, mas os parâmetros das funções sombreiam os nomes e o ruff acusa
# F811 — corretamente, porque ali a importação de fato não é usada.
from alerts.tests.conftest import (  # noqa: E402, F401
    alert_table,
    make_record,
)
