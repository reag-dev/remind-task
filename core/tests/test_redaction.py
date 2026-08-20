"""
RS05 — o que o RedactingFilter tira do log.
"""

import logging

import pytest

from core.logging import MASK, RedactingFilter


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
