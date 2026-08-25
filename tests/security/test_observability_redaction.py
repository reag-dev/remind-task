"""
RS05 na fronteira do rastreador de erro (Phase 9).

O `RedactingFilter` cobre o log. Um APM é outro destino, e o padrão de fábrica
de qualquer SDK é capturar corpo de requisição, cabeçalhos e as variáveis locais
de cada frame do traceback — que é onde o `data` de um registro aparece sem que
ninguém o tenha colocado lá.

Os testes abaixo são sobre o evento MONTADO, do jeito que o SDK o entrega ao
`before_send`: a última chance de olhar antes de virar tráfego de saída.
"""

from core.logging import MASK
from core.observabilidade import antes_de_enviar, opcoes_do_sentry

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhbmEifQ.assinatura-secreta"
CPF = "111.222.333-44"
SENHA = "Contrato!Vencendo#2026"


def evento_com(**partes):
    """Esqueleto de evento do Sentry, com só o que cada teste precisa dentro."""
    return {
        "event_id": "0123456789abcdef0123456789abcdef",
        "level": "error",
        "logger": "django.request",
        **partes,
    }


# --------------------------------------------------- o que não pode sair


def test_o_data_do_registro_nao_sai_no_corpo_da_requisicao():
    evento = antes_de_enviar(
        evento_com(
            request={
                "url": "https://api.exemplo/api/records/",
                "method": "POST",
                "data": {"cliente": "Ana Souza", "cpf": CPF},
            }
        )
    )

    assert evento["request"]["data"] == MASK
    assert CPF not in repr(evento)


def test_o_data_do_registro_nao_sai_nas_locais_do_frame():
    """
    O caminho que ninguém escreve e que vaza mesmo assim.

    Um IntegrityError em `records` sobe com o payload vivo na local `data` do
    frame — o SDK serializa as locais junto do stacktrace por padrão.
    """
    evento = antes_de_enviar(
        evento_com(
            exception={
                "values": [
                    {
                        "type": "IntegrityError",
                        "stacktrace": {
                            "frames": [
                                {
                                    "function": "create",
                                    "vars": {
                                        "data": {"cpf": CPF},
                                        "password": SENHA,
                                        "table_id": "9f8e",
                                    },
                                }
                            ]
                        },
                    }
                ]
            }
        )
    )

    locais = evento["exception"]["values"][0]["stacktrace"]["frames"][0]["vars"]
    assert locais["data"] == MASK
    assert locais["password"] == MASK
    # O que serve ao diagnóstico e não é segredo continua legível — redigir tudo
    # daria um rastreador inútil, e inútil é o começo de "vamos desligar isso".
    assert locais["table_id"] == "9f8e"


def test_o_token_nao_sai_no_cabecalho_nem_no_texto():
    evento = antes_de_enviar(
        evento_com(
            request={"headers": {"Authorization": f"Bearer {JWT}"}},
            message=f"falha ao validar {JWT}",
        )
    )

    assert JWT not in repr(evento)
    assert "assinatura-secreta" not in repr(evento)


def test_a_linha_que_o_postgres_devolve_no_erro_de_constraint():
    """
    `DETAIL: Failing row contains (...)` traz a LINHA inteira, JSONB e tudo.
    Mesmo padrão que o RedactingFilter já cobria no log.
    """
    evento = antes_de_enviar(
        evento_com(
            message=(
                'duplicate key value violates unique constraint\n'
                'DETAIL:  Failing row contains (9f8e, {"cpf": "111.222.333-44"}, 2026-01-01).'
            )
        )
    )

    assert CPF not in evento["message"]
    assert MASK in evento["message"]


def test_o_evento_continua_um_evento():
    """Redigir não pode quebrar a forma — um evento mutilado não é enviado."""
    evento = antes_de_enviar(evento_com(request={"data": {"cpf": CPF}}))

    assert evento["event_id"] == "0123456789abcdef0123456789abcdef"
    assert evento["level"] == "error"
    assert evento["logger"] == "django.request"


def test_hint_e_opcional():
    """O SDK chama com dois argumentos; os testes, com um. Os dois valem."""
    assert antes_de_enviar(evento_com(), {"exc_info": None})["level"] == "error"


# ------------------------------------------------- a configuração em si


def test_a_inicializacao_nao_coleta_pii_nem_corpo():
    """
    As invariantes que um `init(...)` solto não deixaria ninguém afirmar.

    Se alguém acrescentar `send_default_pii=True` por conveniência — é o que
    todo tutorial sugere, para "saber qual usuário viu o erro" —, isto fica
    vermelho antes de virar vazamento.
    """
    opcoes = opcoes_do_sentry("https://chave@sentry.exemplo/1", "producao")

    assert opcoes["send_default_pii"] is False
    assert opcoes["max_request_body_size"] == "never"
    assert opcoes["before_send"] is antes_de_enviar
    assert opcoes["before_send_transaction"] is antes_de_enviar
    assert opcoes["traces_sample_rate"] == 0.0
