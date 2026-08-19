"""
Geração do CSV (RF13).
"""

import csv
from typing import Iterator

from django.db import transaction
from django.utils.text import slugify

from exports.csv_safety import neutralize
from tables.models import ColumnType

CHUNK_SIZE = 500

ALLOWED_DELIMITERS = {",", ";"}

# Excel no Windows assume a codificação local e mostra "ContrÃ¡to" sem isto.
# O BOM é o sinal que faz ele reconhecer UTF-8 ao abrir por duplo clique.
BOM = "﻿"

BOOLEAN_LABELS = {True: "Sim", False: "Não"}


class _Echo:
    """Buffer que devolve o que recebe — o csv.writer escreve direto no stream."""

    def write(self, value):
        return value


def format_cell(value, column) -> str:
    if value is None:
        return ""
    if column.type == ColumnType.BOOLEAN:
        # O cabeçalho já usa os rótulos humanos das colunas; um arquivo para
        # pessoas fica coerente com Sim/Não em vez de true/false.
        return BOOLEAN_LABELS.get(value, "")
    return neutralize(str(value))


def filename_for(table, today) -> str:
    slug = slugify(table.name) or "tabela"
    return f"{slug}-{today.isoformat()}.csv"


def stream_rows(table, columns, queryset, delimiter: str = ",") -> Iterator[str]:
    """
    Gera o CSV linha a linha.

    A transação é aberta AQUI dentro, e não pela request: o corpo de uma
    StreamingHttpResponse é consumido depois que a view retornou, quando a
    transação da request já foi encerrada. Abrir uma própria garante que a
    exportação inteira enxergue um snapshot consistente — e dá à Phase 7 (RLS)
    uma transação viva para o `SET LOCAL app.user_id`.
    """
    if delimiter not in ALLOWED_DELIMITERS:
        delimiter = ","

    writer = csv.writer(_Echo(), delimiter=delimiter, quoting=csv.QUOTE_MINIMAL)

    yield BOM + writer.writerow([column.name for column in columns])

    with transaction.atomic():
        for record in queryset.iterator(chunk_size=CHUNK_SIZE):
            data = record.data or {}
            yield writer.writerow(
                [format_cell(data.get(column.key), column) for column in columns]
            )
