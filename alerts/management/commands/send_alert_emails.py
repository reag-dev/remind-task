"""
Entrega os alertas de e-mail pendentes uma vez e sai.

Existe pelo mesmo motivo que `scan_alerts`: o cron da plataforma é o executor,
e não há serviço `beat` de pé só para disparar uma task.

Comando SEPARADO da varredura, e não um passo dela. Gerar alertas e entregá-los
falham por motivos diferentes — um dado estranho numa tabela versus um servidor
SMTP fora do ar — e juntá-los faria uma indisponibilidade do provedor de e-mail
parar também a geração dos alertas in-app, que não dependem de rede nenhuma.

Para rodar os dois no mesmo cron sem que caiam juntos:

    sh -c "python manage.py scan_alerts; python manage.py send_alert_emails"

Duas coisas nessa linha, e as duas já custaram tempo:

`;` e não `&&` — com `&&`, uma varredura que falhe pularia a entrega dos
pendentes que já estavam na fila, que é exatamente o acoplamento que este
arquivo existe para evitar.

`sh -c` e não os comandos soltos — o Railway executa o start command em **exec
form** para serviço vindo de Dockerfile: não há shell no meio, e `;`, `&&` e
expansão de variável não são interpretados. Sem o invólucro, o `;` vira mais um
argumento do `manage.py` e o comando morre em "unrecognized arguments".
"""

from django.core.management.base import BaseCommand

from alerts.tasks import send_pending_emails


class Command(BaseCommand):
    help = "Entrega os alertas de e-mail pendentes (RF12)."

    def handle(self, *args, **options):
        # Chamada direta, e não `.delay()`: enfileirar faria o processo do cron
        # sair antes de saber se a entrega deu certo.
        desfechos = send_pending_emails()

        resumo = (
            f"E-mails enviados: {desfechos['enviados']} · "
            f"falhas: {desfechos['falhos']} · "
            f"adiados: {desfechos['adiados']}"
        )

        estilo = self.style.WARNING if desfechos["falhos"] else self.style.SUCCESS
        self.stdout.write(estilo(resumo))
