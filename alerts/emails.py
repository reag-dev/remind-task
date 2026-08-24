"""
Montagem do e-mail de vencimento (RF12) sob a regra de vazamento (RS05).

Por que isto é um módulo separado de `tasks.py`
-----------------------------------------------
Montar e entregar falham por motivos diferentes. Um template quebrado é bug de
código; um SMTP fora do ar é indisponibilidade de terceiro. Separados, o teste
do conteúdo — que é onde mora o risco de vazamento — não precisa de rede nem de
banco em estado de fila.

RS05 aplicado ao corpo do e-mail
--------------------------------
O e-mail é a superfície mais exposta que este sistema tem. Diferente de uma
notificação na tela, ele **sai do perímetro**: atravessa o provedor, é indexado
pelo cliente de e-mail do destinatário e fica na caixa de entrada dele para
sempre. Não há "revogar" depois.

Por isso o corpo carrega exatamente três coisas — nome da tabela, vencimento e
um rótulo curto do registro — e o rótulo vem de `record_label()`, o MESMO que
alimenta a notificação in-app, que já pula colunas `is_sensitive`. O `data` do
registro nunca é passado ao template: não há como um campo novo vazar por
esquecimento, porque o template não tem acesso a ele.
"""

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from alerts.services import record_label


def _dias_restantes(alert) -> int:
    """Do disparo até o vencimento. Negativo quando o prazo já passou."""
    return (alert.due_date_snapshot - alert.trigger_date).days


def assunto(alert, rotulo: str) -> str:
    """
    Linha de assunto.

    O rótulo entra aqui porque uma caixa de entrada com cinco avisos idênticos
    é inútil — e ele já é seguro por construção. O que NÃO entra é qualquer
    outro campo do registro: o assunto aparece em notificação de celular, em
    tela de bloqueio e em pré-visualização, sem o usuário ter aberto nada.
    """
    dias = _dias_restantes(alert)
    tabela = alert.record.table.name

    if dias > 0:
        quando = f"vence em {dias} dia{'s' if dias != 1 else ''}"
    elif dias == 0:
        quando = "vence hoje"
    else:
        atraso = abs(dias)
        quando = f"venceu há {atraso} dia{'s' if atraso != 1 else ''}"

    return f"[{tabela}] {rotulo} {quando}"


def montar(alert) -> EmailMultiAlternatives:
    """
    Monta a mensagem de um alerta, sem enviar.

    Devolver o objeto em vez de despachar é o que permite testar o conteúdo —
    inclusive o que ele NÃO contém — sem tocar em transporte.
    """
    colunas = alert.record.table.columns.all()
    rotulo = record_label(alert.record, colunas)

    contexto = {
        "rotulo": rotulo,
        "tabela": alert.record.table.name,
        "vencimento": alert.due_date_snapshot,
        "dias": _dias_restantes(alert),
    }

    mensagem = EmailMultiAlternatives(
        subject=assunto(alert, rotulo),
        body=render_to_string("alerts/vencimento.txt", contexto),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[alert.user.email],
    )
    # Texto como corpo principal e HTML como alternativa, nesta ordem: é o que
    # faz o e-mail continuar legível em cliente que não renderiza HTML, e o que
    # tira dele a cara de mala direta.
    mensagem.attach_alternative(render_to_string("alerts/vencimento.html", contexto), "text/html")
    return mensagem


def enviar(alert) -> None:
    """
    Entrega a mensagem. Levanta a exceção do backend em caso de falha.

    `fail_silently` fica FALSO de propósito: quem decide o que fazer com a falha
    é `tasks.send_pending_emails`, que precisa da exceção para contar a
    tentativa e agendar a próxima. Um envio que engole o erro deixaria o alerta
    marcado como entregue sem ter saído.
    """
    montar(alert).send(fail_silently=False)
