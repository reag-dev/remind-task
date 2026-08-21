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
- O `DETAIL:` de erro do Postgres, que devolve a LINHA inteira que violou a
  constraint — JSONB e tudo.
- Tudo isso também dentro do **traceback**, não só na mensagem.

Por que o `data` inteiro: é ali dentro que mora o valor de uma coluna marcada
`is_sensitive`, e o filtro de log não tem como saber quais chaves de qual tabela
são sensíveis — a definição é por usuário e muda em tempo de execução. Redigir o
payload todo resolve o problema pela raiz, sem registro global nem consulta ao
banco dentro do logger. O rótulo que aparece nas notificações já é montado por
`alerts.services.record_label`, que pula as colunas sensíveis na origem.
"""

import logging
import re
import traceback

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
    # `DETAIL:  Failing row contains (uuid, {"cliente": ..., "cpf": ...}, ...)`
    # — o Postgres devolve a linha INTEIRA quando uma constraint falha, e o
    # psycopg carrega isso na mensagem da exceção. O `.` do regex não casa com
    # newline, então a redação para no fim da linha.
    #
    # O prefixo `DETAIL:` não entra no padrão: a frase já é específica o
    # bastante, e exigir o prefixo deixaria passar qualquer lugar que repasse só
    # o trecho — que é justamente o que uma mensagem de erro reescrita faz.
    (re.compile(r"(?i)(Failing row contains\s*)\(.*"), rf"\1{MASK}"),
    # `DETAIL:  Key (record_id, rule_id, trigger_date)=(...) already exists.`
    # Os NOMES das colunas ficam — são o que serve ao diagnóstico. Os valores saem.
    (re.compile(r"(?i)(Key\s*\([^)]*\)\s*=\s*)\(.*"), rf"\1{MASK}"),
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
    Redige mensagem, argumentos e traceback antes de qualquer handler formatar.

    É um Filter e não um Formatter de propósito: filtros rodam antes da
    formatação, então a redação vale para qualquer formato de saída — texto,
    JSON, o que vier depois.

    Fica ligado ao HANDLER, não ao logger. É a única posição que alcança também
    o que vem de `django.request` e de bibliotecas: filtros de logger não valem
    para registros propagados de loggers filhos. O preço é que cada handler novo
    precisa da sua própria linha de `filters` em `LOGGING` — um handler de
    arquivo ou de APM acrescentado sem ela publicaria tudo em texto puro.
    `tests/security/test_logging_redaction.py::test_every_configured_handler_redacts`
    é o tripwire disso.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if record.args:
            # Ordem obrigatória: redigir os argumentos com a estrutura ainda de
            # pé (é o que permite apagar o `data` de um dict inteiro),
            # RENDERIZAR, e só então passar o regex no texto final.
            #
            # Redigir `record.msg` antes da formatação apagaria os próprios
            # placeholders: `logger.info("token=%s", jti)` viraria
            # `"token=[REDIGIDO]"` com um argumento sobrando, e o `getMessage()`
            # do handler estouraria com `TypeError: not all arguments converted`.
            # O logging engole esse erro em `handleError` — a linha que deveria
            # ser redigida simplesmente não apareceria.
            record.args = scrub(record.args)
            record.msg = scrub(record.getMessage())
            # Já renderizado: zerar evita que o handler tente formatar de novo.
            # Custo assumido: um handler estruturado perde os args separados.
            record.args = None
        else:
            record.msg = scrub(record.msg)

        self._scrub_traceback(record)
        return True

    @staticmethod
    def _scrub_traceback(record: logging.LogRecord) -> None:
        """
        O traceback é o caminho mais provável de vazamento.

        Um `IntegrityError` em `records` faz o psycopg devolver
        `DETAIL: Failing row contains (…)` com o JSONB inteiro dentro, colunas
        `is_sensitive` incluídas. O Django loga isso em `django.request` com
        `exc_info`, e o Formatter renderiza a exceção DEPOIS do filtro — fora do
        alcance de qualquer coisa feita em `record.msg`.

        A saída é preencher `record.exc_text` na frente: o `Formatter` usa o
        valor já pronto e não chama `formatException` de novo.
        """
        if record.exc_info and record.exc_info[0] is not None:
            rendered = "".join(traceback.format_exception(*record.exc_info))
            record.exc_text = scrub(rendered)
        elif record.exc_text:
            record.exc_text = scrub(record.exc_text)

        if record.stack_info:
            record.stack_info = scrub(record.stack_info)
