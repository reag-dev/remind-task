"""
RS05 aplicado ao e-mail — a superfície mais exposta do sistema.

Uma notificação na tela some quando o usuário sai. Um e-mail **atravessa o
perímetro**: passa pelo provedor, é indexado pelo cliente de e-mail de quem
recebe e fica na caixa de entrada dele para sempre. Não existe revogar depois.

Por isso o vazamento é testado aqui, e não junto com a entrega: o que importa é
o CONTEÚDO, e ele não depende de transporte nenhum.

O valor sensível destes testes é um CPF, porque a fixture `alert_table` já marca
essa coluna como `is_sensitive` — a mesma estrutura que o resto da suíte usa.
"""

from datetime import timedelta

import pytest

from alerts.emails import montar
from alerts.models import Alert, AlertChannel, AlertRule, AlertStatus
from alerts.services import generate_for_user
from alerts.tests.conftest import TODAY

# `alert_table` e `make_record` chegam pelo `conftest.py` deste diretório, que
# as re-exporta de `alerts/tests/`. `alert_table` já marca a coluna de CPF como
# `is_sensitive` — é exatamente o que se quer provar que não vaza.

CPF_SECRETO = "529.982.247-25"

pytestmark = pytest.mark.django_db


@pytest.fixture
def alerta_de_email(user, alert_table, make_record):
    """Um alerta de e-mail pendente, sobre um registro com coluna sensível."""
    alert_table.alert_rules.all().delete()
    AlertRule.objects.create(table=alert_table, offset_days=0, channel=AlertChannel.EMAIL)
    make_record(TODAY, cliente="Empresa A", cpf=CPF_SECRETO)

    generate_for_user(user, TODAY)

    return (
        Alert.objects.select_related("record", "record__table", "user")
        .prefetch_related("record__table__columns")
        .get()
    )


def _tudo_que_sai(mensagem) -> str:
    """Assunto, corpo de texto e corpo HTML — tudo que chega ao destinatário."""
    partes = [mensagem.subject, mensagem.body]
    partes += [conteudo for conteudo, _tipo in mensagem.alternatives]
    return "\n".join(partes)


def test_o_valor_da_coluna_sensivel_nao_sai_no_email(alerta_de_email):
    """
    A regressão que este arquivo existe para impedir.

    Nem no assunto, nem no texto, nem no HTML.
    """
    saida = _tudo_que_sai(montar(alerta_de_email))

    assert CPF_SECRETO not in saida
    # Também não pode sair sem a formatação — um `str(data)` de outro jeito.
    assert CPF_SECRETO.replace(".", "").replace("-", "") not in saida


def test_o_json_do_registro_nao_e_passado_ao_template(alerta_de_email):
    """
    A proteção estrutural, e não só o sintoma.

    Se o `data` chegasse ao template, cada campo novo dependeria de alguém
    lembrar de não imprimi-lo. Aqui se mede que ele não chega: nenhuma chave do
    JSONB aparece na saída.
    """
    saida = _tudo_que_sai(montar(alerta_de_email))

    for chave in alerta_de_email.record.data:
        assert f'"{chave}"' not in saida, f"a chave {chave!r} do JSONB vazou"


def test_o_rotulo_seguro_aparece(alerta_de_email):
    """
    O contrapeso: o e-mail precisa ser ÚTIL.

    Sem esta asserção, apagar o corpo inteiro faria os testes acima passarem.
    O que pode aparecer é o rótulo vindo de `record_label()` — a primeira coluna
    não-sensível.
    """
    mensagem = montar(alerta_de_email)
    saida = _tudo_que_sai(mensagem)

    assert "Empresa A" in saida
    assert "Contratos" in saida
    assert mensagem.to == [alerta_de_email.user.email]


def test_marcar_a_coluna_como_sensivel_depois_ja_protege(alerta_de_email, alert_table):
    """
    O rótulo é calculado na LEITURA, não gravado no alerta.

    É isso que faz marcar uma coluna como sensível proteger também os alertas já
    emitidos. Se o rótulo fosse persistido no disparo, esta mudança chegaria
    tarde demais para o que ainda está na fila.
    """
    cliente = alert_table.columns.get(name="Cliente")
    cliente.is_sensitive = True
    cliente.save(update_fields=["is_sensitive"])

    alerta = (
        Alert.objects.select_related("record", "record__table", "user")
        .prefetch_related("record__table__columns")
        .get(pk=alerta_de_email.pk)
    )
    saida = _tudo_que_sai(montar(alerta))

    assert "Empresa A" not in saida
    # Sem coluna utilizável, sobra o id abreviado — identifica sem revelar nada.
    assert str(alerta.record.id)[:8] in saida


def test_o_rotulo_e_escapado_no_html(user, alert_table, make_record):
    """
    O rótulo é conteúdo digitado pelo usuário, e o corpo HTML é markup.

    Um nome de cliente com `<script>` viraria tag no cliente de e-mail de quem
    recebe. O autoescape do Django cobre isso — este teste é o que impede alguém
    de "resolver" um problema de acentuação pondo `{% autoescape off %}` no
    template HTML, como está no .txt.
    """
    alert_table.alert_rules.all().delete()
    AlertRule.objects.create(table=alert_table, offset_days=0, channel=AlertChannel.EMAIL)
    make_record(TODAY, cliente="<script>alert(1)</script>")

    generate_for_user(user, TODAY)
    alerta = (
        Alert.objects.select_related("record", "record__table", "user")
        .prefetch_related("record__table__columns")
        .get()
    )

    html = montar(alerta).alternatives[0][0]

    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_o_alerta_nasce_pendente_esperando_confirmacao(alerta_de_email):
    """A costura que a Phase 5 fecha: e-mail não nasce entregue."""
    assert alerta_de_email.status == AlertStatus.PENDING
    assert alerta_de_email.notified_at is None
    assert alerta_de_email.trigger_date == TODAY - timedelta(days=0)
