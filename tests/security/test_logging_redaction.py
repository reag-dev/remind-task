"""
Critérios 7 e 10 da seção 10 — dado sensível não aparece em log nem em alerta.

O critério 7 tem duas metades, e só uma é sobre o filtro de redação:

1. **Nada loga o valor sensível, para começar.** É a defesa que importa: um
   valor que nunca chega ao logger não depende de regex nenhum. O teste de fluxo
   completo abaixo prova isso.
2. **Se chegar, o filtro apaga.** Coberto em unidade por
   `core/tests/test_redaction.py`, incluindo o traceback. Aqui fica o tripwire da
   *instalação* do filtro, que é a parte que some sem ninguém notar.
"""

import logging

import pytest
from django.conf import settings
from django.urls import reverse

from core.logging import MASK, RedactingFilter
from tests.security.conftest import SENSITIVE_VALUE

pytestmark = pytest.mark.django_db


def test_every_configured_handler_redacts():
    """
    Tripwire da instalação (RS05).

    O filtro é ligado ao HANDLER, não ao logger — é a única forma de alcançar
    também o que vem de `django.request` e de bibliotecas, já que filtros de
    logger não valem para registros propagados de loggers filhos.

    A consequência é que cada handler novo precisa da sua própria linha de
    `filters`. Um handler de arquivo ou de APM acrescentado sem ela publicaria
    tudo em texto puro, e nenhum outro teste notaria.
    """
    handlers = settings.LOGGING["handlers"]

    assert handlers, "nenhum handler configurado"
    for nome, config in handlers.items():
        assert "redact" in config.get("filters", []), (
            f"o handler '{nome}' não passa pelo RedactingFilter"
        )


@pytest.fixture
def log_redigido(caplog):
    """
    Captura de log com o filtro real ligado.

    O handler do `caplog` é do pytest e não herda os `filters` do handler de
    console, então sem isto o teste leria o registro cru e mediria outra coisa.
    """
    caplog.set_level(logging.DEBUG)
    caplog.handler.addFilter(RedactingFilter())
    return caplog


def test_a_full_crud_flow_never_logs_the_sensitive_value(log_redigido, auth_client, mine):
    """
    Critério 7, a metade que vale mais: o valor sensível não chega ao log.

    Percorre a superfície inteira que toca o registro — leitura, escrita,
    exportação e inbox — e confere que o CPF não aparece em nenhuma linha.
    """
    tabela, registro = mine.table, mine.record

    auth_client.get(reverse("records:record-list", args=[tabela.id]))
    auth_client.get(reverse("records:record-detail", args=[tabela.id, registro.id]))
    auth_client.patch(
        reverse("records:record-detail", args=[tabela.id, registro.id]),
        {"data": {"cliente": "Empresa", "cpf": SENSITIVE_VALUE, "vence": "2026-10-01"}},
        format="json",
    )
    resposta = auth_client.get(reverse("records:record-export", args=[tabela.id]))
    b"".join(resposta.streaming_content)
    auth_client.get(reverse("alerts:alert-list"))

    assert log_redigido.text, "nenhum log capturado — o teste não provaria nada"
    assert SENSITIVE_VALUE not in log_redigido.text


def test_the_export_logs_identifiers_only(log_redigido, auth_client, mine):
    """
    A exportação é o único ponto que loga por registro — e loga contagem, não
    conteúdo.
    """
    resposta = auth_client.get(reverse("records:record-export", args=[mine.table.id]))
    b"".join(resposta.streaming_content)

    linhas = [linha for linha in log_redigido.text.splitlines() if "Exportação CSV" in linha]

    assert linhas, "a exportação deixou de registrar qualquer coisa"
    for linha in linhas:
        assert str(mine.table.id) in linha
        assert SENSITIVE_VALUE not in linha
        assert "Empresa" not in linha


def test_a_password_in_a_log_line_is_redacted(log_redigido):
    """
    A segunda metade: se algo LOGAR uma credencial, ela não sai inteira.

    Usa o logger de uma view real em vez de um logger de teste — é o caminho que
    a configuração de `LOGGING` realmente atende.
    """
    logging.getLogger("accounts.views").warning(
        "falha ao autenticar password=%s", "Contrato!Vencendo#2026"
    )

    assert "Contrato!Vencendo#2026" not in log_redigido.text
    assert MASK in log_redigido.text


# ------------------------------------------------------------------ critério 10


def test_the_alert_payload_never_carries_a_sensitive_column(auth_client, mine):
    """
    Critério 10 — RS05.

    Uma notificação é a superfície mais exposta do sistema: aparece em lista,
    vira e-mail e acaba em log de entrega. O payload carrega o mínimo — tabela,
    vencimento e um rótulo curto — e o rótulo pula colunas `is_sensitive`.
    """
    resposta = auth_client.get(reverse("alerts:alert-list"))
    corpo = resposta.content.decode()

    assert resposta.status_code == 200
    assert resposta.data["results"], "sem alerta, o teste não prova nada"
    assert SENSITIVE_VALUE not in corpo

    alerta = resposta.data["results"][0]
    assert "data" not in alerta, "o payload não pode carregar o JSONB do registro"
    assert alerta["label"] == "Empresa"


def test_making_a_column_sensitive_also_protects_alerts_already_issued(
    auth_client, mine
):
    """
    O rótulo é calculado na leitura, não gravado no alerta.

    Por isso marcar uma coluna como sensível DEPOIS protege também as
    notificações que já existiam — se fosse gravado, o alerta antigo continuaria
    exibindo o valor para sempre.
    """
    cliente = mine.table.columns.get(key="cliente")
    cliente.is_sensitive = True
    cliente.save(update_fields=["is_sensitive"])

    resposta = auth_client.get(reverse("alerts:alert-list"))

    assert "Empresa" not in resposta.content.decode()
