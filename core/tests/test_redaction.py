"""
RS05 — o que o RedactingFilter tira do log.
"""

import logging
import sys

import pytest

from core.logging import MASK, RedactingFilter


@pytest.fixture
def record_with_exception():
    """LogRecord carregando uma exceção, como o handler de 500 do Django monta."""

    def _make(message):
        try:
            raise ValueError(message)
        except ValueError:
            return logging.LogRecord(
                "django.request", logging.ERROR, __file__, 1,
                "Internal Server Error: /api/tables/", None, sys.exc_info(),
            )

    return _make


@pytest.fixture
def redact():
    log_filter = RedactingFilter()

    def _apply(msg, *args):
        record = logging.LogRecord(
            "teste", logging.INFO, __file__, 1, msg, args or None, None
        )
        log_filter.filter(record)
        return record.getMessage()

    return _apply


@pytest.mark.parametrize(
    "line",
    [
        "login falhou password=Contrato!Vencendo#2026",
        'payload {"token": "abc123def456"}',
        "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.assinatura",
        "GET /api/auth/refresh/?token=abc123def456",
        "hash argon2$argon2id$v=19$m=102400,t=2,p=8$c2FsdA$aGFzaA",
    ],
)
def test_credentials_never_reach_the_handler(redact, line):
    output = redact(line)

    assert MASK in output
    for leaked in ("Contrato!Vencendo#2026", "abc123def456", "assinatura", "aGFzaA"):
        assert leaked not in output


def test_record_payload_is_redacted_whole(redact):
    """
    O `data` inteiro sai, não só as chaves com nome suspeito.

    O filtro não tem como saber quais colunas daquela tabela estão marcadas
    `is_sensitive` — a definição é por usuário e muda em tempo de execução.
    Redigir o payload todo é o que torna a garantia independente disso.
    """
    output = redact(
        "registro salvo %s", {"id": "abc", "data": {"responsavel": "João", "cpf": "123"}}
    )

    assert "João" not in output
    assert "123" not in output
    assert MASK in output
    assert "abc" in output  # identificador continua legível: é o que serve ao debug


def test_ordinary_lines_pass_through_untouched(redact):
    assert redact("Exportação CSV: tabela=%s colunas=%s", "abc-123", 5) == (
        "Exportação CSV: tabela=abc-123 colunas=5"
    )


# ---------------------------------------------------------------- traceback


def test_placeholders_survive_the_redaction(redact):
    """
    Redigir a mensagem ANTES da formatação apagaria o próprio `%s`.

    `logger.info("token=%s", jti)` viraria `"token=[REDIGIDO]"` com um argumento
    sobrando, e o `getMessage()` do handler estouraria com
    `TypeError: not all arguments converted`. O logging engole esse erro em
    `handleError` — a linha que deveria ser redigida sumiria do log.
    """
    output = redact("token=%s emitido para %s", "jti-abc-123", "ana")

    assert "jti-abc-123" not in output
    assert MASK in output
    assert "emitido para ana" in output


def test_the_traceback_is_redacted_too(record_with_exception):
    """
    O caminho mais provável de vazamento (RS05).

    Um IntegrityError em `records` faz o psycopg devolver `Failing row contains`
    com o JSONB inteiro dentro — colunas `is_sensitive` incluídas. O Django loga
    isso em `django.request` com `exc_info`, e o Formatter renderiza a exceção
    DEPOIS do filtro: nada feito em `record.msg` alcança aquele texto.
    """
    log_record = record_with_exception(
        'new row for relation "records" violates check constraint\n'
        'DETAIL:  Failing row contains (abc-123, {"responsavel": "João", "cpf": "111"}).'
    )

    RedactingFilter().filter(log_record)
    output = logging.Formatter("%(message)s").format(log_record)

    assert "João" not in output
    assert "111" not in output
    assert MASK in output
    # O diagnóstico continua possível: o nome da constraint sobrevive.
    assert "violates check constraint" in output


def test_unique_violation_keeps_the_column_names_and_drops_the_values(redact):
    output = redact(
        "erro: Key (record_id, rule_id, trigger_date)"
        "=(abc-123, def-456, 2026-08-20) already exists."
    )

    assert "record_id, rule_id, trigger_date" in output
    assert "abc-123" not in output
    assert "def-456" not in output
