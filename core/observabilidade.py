"""
O que pode sair daqui para um rastreador de erro (RS05).

Um APM é um destino de dados como qualquer outro — e dos piores, porque o
padrão da indústria é capturar TUDO: corpo da requisição, cabeçalhos, cookies e
as variáveis locais de cada frame do traceback. Um `IntegrityError` em
`records` carrega o `data` inteiro do registro nas locais do frame, colunas
`is_sensitive` incluídas. Ligar um SDK com a configuração de fábrica desfaz, num
comando, a proteção que `core/logging.py` construiu.

A regra aqui é a mesma do `RedactingFilter`, aplicada no último ponto possível:
o evento já montado, imediatamente antes de sair pela rede.

Por que no `before_send` e não confiando no filtro de log
---------------------------------------------------------
O `RedactingFilter` está pendurado nos HANDLERS (ver a nota em
`core/logging.py`). A integração de logging do SDK não é um handler nosso: ela
se enxerta no caminho do `logging` e enxerga o `LogRecord` por conta própria. Se
o registro chega a ela antes de passar por um handler nosso, chega **em claro** —
a redação depende de ordem, e ordem entre bibliotecas não é contrato.

`before_send` não depende de ordem nenhuma: é o último ponto antes do envio, e
todo evento passa por ele — os que vieram de log, os que vieram de exceção não
tratada e os que uma biblioteca resolveu mandar sozinha.
"""

from core.logging import scrub


def antes_de_enviar(event, hint=None):
    """
    Redige o evento inteiro, preservando a forma.

    O `scrub` percorre dicts, listas e strings: apaga por NOME de chave
    (`password`, `token`, `data`, `authorization`…) e por PADRÃO no texto (JWT,
    hash de senha, `Failing row contains (...)`). Isso alcança de uma vez o
    corpo da requisição, os cabeçalhos, os breadcrumbs, o `extra` e as variáveis
    locais de cada frame — que é onde o `data` de um registro costuma estar sem
    que ninguém tenha escrito uma linha para colocá-lo lá.

    `hint` não é usado, e o parâmetro existe porque a assinatura é do SDK.
    """
    return scrub(event)


def opcoes_do_sentry(dsn, ambiente, taxa_de_traces=0.0):
    """
    As opções da inicialização, num lugar que o teste alcança sem subir o SDK.

    Elas moravam soltas dentro do `sentry_sdk.init(...)` em `prod.py`, e o
    problema é que ninguém consegue afirmar nada sobre uma chamada — só sobre um
    valor. Aqui `tests/security/test_observability_redaction.py` verifica cada
    invariante, e um `send_default_pii=True` acrescentado por conveniência vira
    teste vermelho em vez de vazamento silencioso.
    """
    return {
        "dsn": dsn,
        "environment": ambiente,
        # PII desligado: sem IP do cliente, sem cookies, sem identidade do
        # usuário anexada ao evento.
        "send_default_pii": False,
        # O corpo da requisição NUNCA. É onde trafega o `data` do registro —
        # exatamente o que o RS05 protege. `before_send` já redigiria, mas não
        # coletar é mais barato e não depende de o `scrub` estar certo.
        "max_request_body_size": "never",
        "before_send": antes_de_enviar,
        # Transações carregam a mesma estrutura de contexto. Com
        # `taxa_de_traces=0` nenhuma é gerada, e é justamente por isso que a
        # linha precisa existir agora: quem ligar tracing depois não vai lembrar
        # de acrescentá-la.
        "before_send_transaction": antes_de_enviar,
        "traces_sample_rate": taxa_de_traces,
    }
