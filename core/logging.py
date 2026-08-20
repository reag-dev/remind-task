"""
Redação de dados sensíveis no log (RS05).

Log é um destino que ninguém trata como banco de dados: vai para stdout, é
agregado, fica retido por meses e costuma ser lido por mais gente do que tem
acesso à aplicação. Uma senha, um refresh token ou o conteúdo de um registro que
caia aqui vaza sem que nenhuma proteção da API tenha falhado.

O que é apagado
---------------
- Chaves de credencial: `password`, `senha`, `token`, `secret`, `authorization`,
  `api_key`, `refresh`, `access`.
- Hashes de senha (`argon2$...`, `pbkdf2_sha256$...`) e JWTs (`eyJ....`).
- Cabeçalhos `Authorization: Bearer ...`.
- O `data` dos registros, **inteiro**.

Por que o `data` inteiro: é ali dentro que mora o valor de uma coluna marcada
`is_sensitive`, e o filtro de log não tem como saber quais chaves de qual tabela
são sensíveis — a definição é por usuário e muda em tempo de execução. Redigir o
payload todo resolve o problema pela raiz, sem registro global nem consulta ao
banco dentro do logger. O rótulo que aparece nas notificações já é montado por
`alerts.services.record_label`, que pula as colunas sensíveis na origem.
"""

import logging
import re

MASK = "[REDIGIDO]"

SENSITIVE_KEY = re.compile(
    r"^(?:.*_)?(password|senha|token|secret|authorization|api[_-]?key|refresh|access|data|valores)$",
    re.IGNORECASE,
)

_PATTERNS = (
    # Authorization: Bearer <jwt>  /  Basic <b64>
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"), rf"\1 {MASK}"),
    # Qualquer JWT solto, mesmo sem a palavra-chave por perto.
    (re.compile(r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"), MASK),
    # Hash de senha do Django, no formato algoritmo$parâmetros$hash.
    (re.compile(r"\b(argon2|pbkdf2_[a-z0-9]+|scrypt|bcrypt)\$\S+"), rf"\1${MASK}"),
    # chave=valor / "chave": "valor" / chave: valor
    (
        re.compile(
            r"(?i)([\"']?\b(?:password|senha|token|secret|authorization|api[_-]?key)\b[\"']?"
            r"\s*[:=]\s*)([\"']?)([^\s,;&}\)\]\"']+)\2"
        ),
        rf"\1\2{MASK}\2",
    ),
)


def scrub(value):
    """Versão redigida de `value`, preservando a forma (dict, lista, texto)."""
    if isinstance(value, dict):
        return {
            key: MASK if SENSITIVE_KEY.match(str(key)) else scrub(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        cleaned = [scrub(item) for item in value]
        return type(value)(cleaned) if not isinstance(value, tuple) else tuple(cleaned)
    if isinstance(value, str):
        for pattern, replacement in _PATTERNS:
            value = pattern.sub(replacement, value)
        return value
    return value


class RedactingFilter(logging.Filter):
    """
    Aplica `scrub` na mensagem e nos argumentos antes da formatação.

    É um Filter e não um Formatter de propósito: filtros rodam antes de o
    handler formatar, então a redação vale para qualquer formato de saída
    (texto, JSON, o que vier depois) e também para os handlers que outra pessoa
    acrescentar mais tarde.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = scrub(record.msg)

        if record.args:
            record.args = scrub(record.args)

        return True
