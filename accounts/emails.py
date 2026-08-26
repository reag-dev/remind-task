"""
O e-mail de recuperação de senha (Phase 10), sob a mesma regra do RS05.

Módulo separado da view pelo mesmo motivo que `alerts/emails.py` é separado de
`alerts/tasks.py`: montar e entregar falham por motivos diferentes, e o teste do
CONTEÚDO — que é onde mora o risco — não deveria precisar de transporte.

O que este e-mail carrega, e o que não carrega
----------------------------------------------
Carrega: o nome, o próprio endereço de destino, o link e a validade. Não carrega
nenhum dado de tabela ou registro, e não repete a senha antiga nem sugere uma
nova. O link já é o segredo; qualquer coisa a mais só aumenta o que vaza se a
caixa do destinatário for comprometida.

Só texto, sem alternativa HTML — diferente do e-mail de vencimento. Aqui o
conteúdo é uma frase e uma URL: um corpo HTML acrescentaria só a chance de o
cliente de e-mail transformar o link em algo que o usuário não consegue
inspecionar antes de clicar, que é exatamente o hábito que se quer do outro lado.
"""

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


def montar_link(user) -> str:
    """
    O link aponta para a SPA, não para a API.

    Quem renderiza o formulário de nova senha é o frontend; mandar o usuário
    para um endpoint DRF seria entregá-lo à browsable API — ou a um 405 em
    produção, onde ela não sobe.
    """
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return f"{settings.FRONTEND_URL}/redefinir-senha?uid={uid}&token={token}"


def montar(user) -> EmailMessage:
    """Monta a mensagem, sem enviar — é o que permite testar o conteúdo."""
    contexto = {
        "nome": user.name or user.email,
        "email": user.email,
        "link": montar_link(user),
        "validade_em_horas": max(1, settings.PASSWORD_RESET_TIMEOUT // 3600),
    }

    return EmailMessage(
        subject="Redefinição de senha — remind-task",
        body=render_to_string("accounts/redefinir_senha.txt", contexto),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )


def enviar(user) -> None:
    """
    Entrega a mensagem.

    `fail_silently=True`, ao contrário do envio de alertas — e a diferença é
    deliberada. Lá, a falha precisa subir para a task contar a tentativa e
    reagendar. Aqui, deixar a exceção subir mudaria a RESPOSTA da requisição
    conforme o e-mail existisse ou não: endereço sem conta nunca tenta enviar e
    devolve 204; endereço com conta, num momento de SMTP fora do ar, devolveria
    500. O endpoint viraria justamente o oráculo de cadastro que ele foi
    desenhado para não ser.

    A falha não some: `send()` com `fail_silently=True` engole a exceção do
    backend, e o log de erro é o registro. Quem opera o sistema vê; quem sonda
    de fora, não.
    """
    montar(user).send(fail_silently=True)


# ------------------------------------------------- exclusão de conta (Phase 11)


def montar_exclusao(email: str, nome: str, quando, resumo: dict) -> EmailMessage:
    """
    O aviso de conta excluída.

    Recebe primitivos, e não o objeto `user`, porque quando isto é chamado a
    LINHA JÁ NÃO EXISTE — o e-mail sai depois do commit da exclusão (ver
    `AccountDeleteView`). Passar a instância aqui daria um objeto zumbi, com pk
    apontando para nada, e qualquer acesso a relação levantaria exceção no meio
    da montagem do template.

    O resumo do que foi apagado não é enfeite: é como o dono de uma conta
    comprometida descobre o tamanho do estrago. Só CONTAGENS, nunca conteúdo —
    o corpo de um registro nunca sai por e-mail (RS05), e menos ainda num aviso
    que a pessoa talvez não tenha pedido.
    """
    contexto = {"nome": nome, "email": email, "quando": quando, **resumo}

    return EmailMessage(
        subject="Sua conta no remind-task foi excluída",
        body=render_to_string("accounts/conta_excluida.txt", contexto),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email],
    )


def enviar_exclusao(email: str, nome: str, quando, resumo: dict) -> None:
    """
    Entrega o aviso.

    `fail_silently=True` como no de recuperação, por um motivo diferente: aqui a
    conta JÁ FOI apagada quando o envio acontece. Deixar a exceção do SMTP subir
    não desfaria nada — só transformaria uma exclusão bem-sucedida em 500 na
    tela de quem a pediu, sugerindo que ela falhou. O erro vai para o log.
    """
    montar_exclusao(email, nome, quando, resumo).send(fail_silently=True)
