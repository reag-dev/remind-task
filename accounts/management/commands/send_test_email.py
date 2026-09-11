"""
Manda um e-mail de teste real, sem engolir falha nenhuma.

Existe porque nada na suíte de testes prova o transporte de produção: os
testes usam o backend `locmem`, que aceita qualquer coisa. `accounts.emails`
também não serve para provar isto — `enviar()` e `enviar_exclusao()` engolem a
exceção de propósito (RS-oráculo de cadastro), então rodá-los aqui mostraria
"sucesso" mesmo com o provedor rejeitando tudo.

Uso, depois de configurar EMAIL_BACKEND/ANYMAIL/DEFAULT_FROM_EMAIL:

    python manage.py send_test_email seu@email.com
"""

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Manda um e-mail de teste pelo EMAIL_BACKEND configurado, sem fail_silently."

    def add_arguments(self, parser):
        parser.add_argument("destinatario", help="Endereço que recebe o teste.")

    def handle(self, *args, **options):
        destinatario = options["destinatario"]

        mensagem = EmailMessage(
            subject="remind-task — e-mail de teste",
            body=(
                f"Backend: {settings.EMAIL_BACKEND}\n"
                f"Remetente: {settings.DEFAULT_FROM_EMAIL}\n\n"
                "Se isto chegou, o transporte configurado está entregando."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[destinatario],
        )

        try:
            mensagem.send(fail_silently=False)
        except Exception as erro:
            raise CommandError(f"Envio falhou: {erro!r}") from erro

        self.stdout.write(self.style.SUCCESS(f"Enviado para {destinatario}."))
