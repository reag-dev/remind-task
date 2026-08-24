"""
Roda a varredura de vencimentos uma vez e sai.

Existe para o cron da plataforma. A Phase 3 do plano questionou o serviço
`beat`: é um processo ocioso 24 horas por dia para disparar **uma** task a cada
15 minutos. O `cronSchedule` do Railway faz o mesmo sem serviço parado de pé, e
a escolha é de custo — não de correção.

Repetição é segura: a constraint `alerts_idempotency` sobre
`(record, rule, trigger_date)` impede duplicata mesmo com execuções sobrepostas.
Isso é o que torna o cron aceitável: se um disparo atrasar e cair em cima do
seguinte, nada corrompe.
"""

from django.core.management.base import BaseCommand

from alerts.tasks import scan_due_records


class Command(BaseCommand):
    help = "Varre os vencimentos e emite os alertas devidos (RF12)."

    def handle(self, *args, **options):
        # Chamada direta, e não `.delay()`: o cron É o executor. Enfileirar aqui
        # só transferiria o trabalho para o worker e faria o processo do cron
        # sair antes de saber se deu certo — um disparo que falha em silêncio.
        criados = scan_due_records()

        self.stdout.write(self.style.SUCCESS(f"Alertas gerados: {criados}"))
