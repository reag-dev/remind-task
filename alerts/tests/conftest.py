from datetime import date

import pytest

from records.models import Record
from tables.models import Column, ColumnType, Table

TODAY = date(2026, 8, 19)


@pytest.fixture
def alert_table(db, user):
    """
    Tabela com coluna de vencimento, um rótulo comum e um campo sensível.

    O sinal cria a regra padrão (offset = alert_lead_days = 3) assim que a coluna
    de vencimento nasce.
    """
    table = Table.objects.create(user=user, name="Contratos", alert_lead_days=3)
    Column.objects.create(table=table, name="Cliente", type=ColumnType.TEXT, position=0)
    Column.objects.create(
        table=table, name="CPF", type=ColumnType.TEXT, position=1, is_sensitive=True
    )
    Column.objects.create(
        table=table, name="Vence", type=ColumnType.DUE_DATE, position=2
    )
    return table


@pytest.fixture
def default_rule(alert_table):
    return alert_table.alert_rules.get()


def add_record(table, due: date | None, cliente="Empresa A", cpf="000.000.000-00"):
    return Record.objects.create(
        table=table,
        data={
            "cliente": cliente,
            "cpf": cpf,
            "vence": due.isoformat() if due else None,
        },
    )


@pytest.fixture
def make_record(alert_table):
    def _make(due, **kwargs):
        return add_record(alert_table, due, **kwargs)

    return _make
