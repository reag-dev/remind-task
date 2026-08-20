"""
`manage.py seed_demo` — a porta de entrada de quem acabou de clonar o repo.
"""

from datetime import date, timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from freezegun import freeze_time

from alerts.models import Alert
from records.models import Record
from records.status import DueStatus
from tables.models import Table

pytestmark = pytest.mark.django_db

# Meio-dia UTC de propósito: a conta demo vive em America/Sao_Paulo (UTC-3), e
# congelar o relógio à meia-noite UTC colocaria o usuário no dia ANTERIOR. O
# comportamento está certo — é o que `core/dates.py` existe para fazer — mas
# transformaria cada asserção de data num quebra-cabeça de fuso.
HOJE = date(2026, 8, 20)
MEIO_DIA = f"{HOJE.isoformat()} 12:00:00"


def semear(**kwargs):
    saida = StringIO()
    call_command("seed_demo", stdout=saida, force=True, **kwargs)
    return saida.getvalue()


def test_it_refuses_to_run_with_debug_off():
    """
    A conta demo tem senha conhecida e publicada no README.

    Em produção isso não é dado de demonstração, é uma porta aberta. O comando
    exige `--force` para rodar fora de DEBUG — a barreira é ser difícil de fazer
    por acidente, não impossível de fazer de propósito.
    """
    with override_settings(DEBUG=False), pytest.raises(CommandError, match="DEBUG=False"):
        call_command("seed_demo", stdout=StringIO())


def test_it_creates_the_example_from_the_specification():
    semear()

    table = Table.objects.get(name="Contratos")

    assert table.user.email == "demo@remind.local"
    assert [c.name for c in table.columns.all()] == [
        "Cliente",
        "Contrato",
        "Responsável",
        "Data de vencimento",
        "Status",
    ]
    assert table.records.count() == 3


def test_the_responsible_column_is_marked_sensitive():
    """RS05 — o exemplo já nasce mostrando para que serve `is_sensitive`."""
    semear()

    coluna = Table.objects.get(name="Contratos").columns.get(name="Responsável")

    assert coluna.is_sensitive


@freeze_time(MEIO_DIA)
def test_the_three_due_statuses_of_the_example_are_reproduced():
    """
    O ponto do exemplo da seção 7: vencido → vence em breve → futuro.

    As datas do documento são absolutas (15, 20 e 25/08/2026). O seed usa
    offsets, senão uma semana depois os três contratos estariam vencidos e a
    demonstração perderia exatamente o que ela existe para mostrar.
    """
    semear()

    table = Table.objects.get(name="Contratos")
    chave = table.columns.get(name="Cliente").key
    registros = Record.objects.filter(table=table).with_due_status(HOJE)

    status = {r.data[chave]: r.due_status for r in registros}

    assert status == {
        "Empresa C": DueStatus.OVERDUE,
        "Empresa A": DueStatus.DUE_SOON,
        "Empresa B": DueStatus.ON_TRACK,
    }


def test_running_it_twice_does_not_duplicate_anything():
    semear()
    semear()

    table = Table.objects.get(name="Contratos")

    assert Table.objects.filter(name="Contratos").count() == 1
    assert table.columns.count() == 5
    assert table.records.count() == 3


def test_a_second_run_refreshes_the_dates_instead_of_skipping():
    """
    Idempotente aqui significa CONVERGIR, não pular.

    Semear em janeiro e rodar de novo em março tem de devolver a demonstração ao
    estado útil — três contratos em três estados — e não deixar os três vencidos.
    """
    with freeze_time("2026-01-10 12:00:00"):
        semear()
        antes = sorted(Record.objects.values_list("due_date", flat=True))

    with freeze_time("2026-03-10 12:00:00"):
        semear()
        depois = sorted(Record.objects.values_list("due_date", flat=True))

    assert antes != depois
    assert depois == [date(2026, 3, 10) + timedelta(days=n) for n in (-5, 2, 30)]


def test_the_inbox_is_not_empty_after_seeding():
    """Sem alerta nenhum, `/api/alerts/` seria uma tela vazia na demonstração."""
    semear()

    assert Alert.objects.filter(user__email="demo@remind.local").exists()


def test_the_credentials_are_printed():
    saida = semear()

    assert "demo@remind.local" in saida
    assert "/api/docs/" in saida
