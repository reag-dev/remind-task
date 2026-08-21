"""
Popula o banco com o exemplo da seção 7 da especificação.

Serve para o "clonei o repo, e agora?": depois deste comando existe uma conta com
dado real dentro, e dá para exercitar a API inteira pela Browsable API ou pelo
Swagger sem cadastrar nada à mão.
"""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from alerts.services import generate_for_user
from core.dates import user_today
from records.models import Record
from tables.models import Column, ColumnType, Table

DEMO_EMAIL = "demo@remind.local"
DEMO_PASSWORD = "Contrato!Vencendo#2026"
DEMO_NAME = "Conta Demo"

TABLE_NAME = "Contratos"
ALERT_LEAD_DAYS = 3

# (rótulo, tipo, extras) — a estrutura da tabela do exemplo.
COLUMNS = [
    ("Cliente", ColumnType.TEXT, {}),
    ("Contrato", ColumnType.TEXT, {"is_required": True}),
    # RS05: o responsável é dado pessoal. Marcado como sensível, some do rótulo
    # das notificações e do log.
    ("Responsável", ColumnType.TEXT, {"is_sensitive": True}),
    ("Data de vencimento", ColumnType.DUE_DATE, {"is_required": True}),
    ("Status", ColumnType.SELECT, {"options": ["Ativo", "Encerrado"]}),
]

# As datas do documento (15, 20 e 25/08/2026) são ABSOLUTAS. Usá-las literalmente
# faria o seed envelhecer: uma semana depois os três contratos estariam vencidos
# e a demonstração perderia justamente o que ela existe para mostrar. O offset
# reproduz os três estados do exemplo — vencido, vence em breve, futuro — em
# qualquer dia em que o comando rodar.
ROWS = [
    # (cliente, contrato, responsável, dias a partir de hoje)
    ("Empresa C", "CT-003", "Pedro", -5),   # overdue
    ("Empresa A", "CT-001", "João", +2),    # due_soon (dentro do alert_lead_days)
    ("Empresa B", "CT-002", "Maria", +30),  # on_track
]


class Command(BaseCommand):
    help = "Cria a conta demo e a tabela Contratos do exemplo da especificação."

    def add_arguments(self, parser):
        parser.add_argument("--email", default=DEMO_EMAIL)
        parser.add_argument("--password", default=DEMO_PASSWORD)
        parser.add_argument(
            "--force",
            action="store_true",
            help="roda mesmo com DEBUG=False (não use em produção).",
        )

    def handle(self, *args, **options):
        # O comando cria uma conta com senha conhecida e publicada no README.
        # Em produção isso é uma porta aberta, não um dado de demonstração.
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "seed_demo cria uma conta com senha conhecida e está bloqueado "
                "com DEBUG=False. Use --force se souber o que está fazendo."
            )

        with transaction.atomic():
            user, criado = self._user(options["email"], options["password"])
            table = self._table(user)
            columns = self._columns(table)
            records = self._records(table, columns)
            alertas = generate_for_user(user, user_today(user))

        self._report(user, criado, options["password"], table, records, alertas)

    # ------------------------------------------------------------------ passos

    def _user(self, email, password):
        User = get_user_model()
        user, criado = User.objects.get_or_create(
            email=email, defaults={"name": DEMO_NAME}
        )
        # A senha é redefinida mesmo numa conta que já existia: o comando é a
        # fonte da verdade sobre como entrar nela.
        user.set_password(password)
        user.save(update_fields=["password"])
        return user, criado

    def _table(self, user):
        table, _ = Table.objects.get_or_create(
            user=user,
            name=TABLE_NAME,
            defaults={
                "description": "Exemplo da seção 7 da especificação.",
                "alert_lead_days": ALERT_LEAD_DAYS,
            },
        )
        return table

    def _columns(self, table):
        for posicao, (nome, tipo, extras) in enumerate(COLUMNS):
            Column.objects.get_or_create(
                table=table,
                name=nome,
                defaults={"type": tipo, "position": posicao, **extras},
            )
        return {column.name: column for column in table.columns.all()}

    def _records(self, table, columns):
        """
        Converge para o estado desejado em vez de pular o que já existe.

        Se o comando só criasse na primeira vez, rodar de novo uma semana depois
        deixaria os três contratos vencidos — e as datas relativas não teriam
        servido para nada.
        """
        hoje = user_today(table.user)
        chaves = {nome: column.key for nome, column in columns.items()}

        criados = []
        for cliente, contrato, responsavel, offset in ROWS:
            data = {
                chaves["Cliente"]: cliente,
                chaves["Contrato"]: contrato,
                chaves["Responsável"]: responsavel,
                chaves["Data de vencimento"]: (hoje + timedelta(days=offset)).isoformat(),
                chaves["Status"]: "Ativo",
            }
            record = Record.objects.filter(
                table=table, **{f"data__{chaves['Contrato']}": contrato}
            ).first()

            if record is None:
                record = Record.objects.create(table=table, data=data)
            else:
                record.data = data
                record.save()

            criados.append(record)
        return criados

    # ------------------------------------------------------------------ saída

    def _report(self, user, criado, password, table, records, alertas):
        escrever = self.stdout.write
        ok = self.style.SUCCESS

        escrever(ok(f"\n{'Conta criada' if criado else 'Conta já existia (senha redefinida)'}"))
        escrever(f"  e-mail ..... {user.email}")
        escrever(f"  senha ...... {password}")
        escrever(f"  fuso ....... {user.timezone}")

        escrever(ok(f"\nTabela '{table.name}' — {len(records)} registros"))
        for record in sorted(records, key=lambda r: r.due_date):
            chave_cliente = table.columns.get(name="Cliente").key
            escrever(
                f"  {record.data[chave_cliente]:<12} vence {record.due_date}"
            )

        escrever(ok(f"\n{alertas} alerta(s) gerado(s) para a caixa de entrada"))

        escrever(ok("\nPor onde começar"))
        escrever("  http://localhost:8000/api/docs/    Swagger (clique em Authorize)")
        escrever("  http://localhost:8000/api/tables/  Browsable API do DRF")
        escrever("  http://localhost:8000/admin/       Admin (precisa de createsuperuser)")
        escrever("")
