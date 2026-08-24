"""
Checagem do banco ANTES do primeiro `migrate`.

A Phase 3 do plano de produção registrou o risco: se o Postgres gerenciado não
permitir `CREATE ROLE`, `core/migrations/0001_rls_policies` falha **no meio** da
sequência de migrations — deixando o schema pela metade, que é bem pior do que
não ter começado.

Este comando responde às perguntas antes disso, contra o banco de verdade, e
sem deixar nada para trás: tudo o que ele cria acontece dentro de uma transação
que termina em ROLLBACK.

    railway run --service web python manage.py preflight_db
"""

from django.core.management.base import BaseCommand
from django.db import connection, transaction

ROLE_DE_TESTE = "remind_preflight_probe"

# O `docker/postgres/init.sql` cria `citext` e `pgcrypto`, mas **nenhuma das
# duas é usada**: o e-mail case-insensitive virou collation ICU quando o Django
# 5.1 removeu `CIEmailField`, e os UUIDs vêm de `uuid.uuid4` em Python. Ficam
# aqui como informação, não como requisito — é o oposto do que o plano supunha.
EXTENSOES_INFORMATIVAS = ("citext", "pgcrypto")


class Falha(Exception):
    """Checagem obrigatória que não passou."""


class Command(BaseCommand):
    help = "Verifica se o banco suporta o que as migrations vão exigir."

    def handle(self, *args, **options):
        obrigatorias = [
            ("versao do Postgres", self._versao),
            ("ICU disponivel (e-mail case-insensitive)", self._icu),
            ("CREATE ROLE (RLS - RS01)", self._create_role),
            ("GRANT do papel ao usuario atual", self._grant_role),
            ("RLS aplicavel as tabelas", self._row_level_security),
        ]

        falhou = False
        for titulo, checagem in obrigatorias:
            try:
                detalhe = checagem()
            except Falha as erro:
                falhou = True
                self.stdout.write(self.style.ERROR(f"  FALHOU  {titulo}"))
                self.stdout.write(f"          {erro}")
            except Exception as erro:
                falhou = True
                self.stdout.write(self.style.ERROR(f"  ERRO    {titulo}"))
                self.stdout.write(f"          {type(erro).__name__}: {erro}")
            else:
                self.stdout.write(self.style.SUCCESS(f"  ok      {titulo}"))
                if detalhe:
                    self.stdout.write(f"          {detalhe}")

        self.stdout.write("")
        self.stdout.write("Informativo (nada aqui bloqueia o deploy):")
        for extensao in EXTENSOES_INFORMATIVAS:
            estado = "disponivel" if self._extensao_disponivel(extensao) else "ausente"
            self.stdout.write(f"  {extensao:10s} {estado} - nao usada pela aplicacao")

        self.stdout.write("")
        if falhou:
            self.stdout.write(
                self.style.ERROR(
                    "NAO rode `migrate`. Uma checagem obrigatoria falhou, e a "
                    "migration de RLS quebraria no meio da sequencia."
                )
            )
            # Saída != 0 para que isto sirva de gate num pipeline.
            raise SystemExit(1)

        self.stdout.write(self.style.SUCCESS("Banco apto. Pode rodar `migrate`."))

    # ------------------------------------------------------------ checagens

    def _versao(self) -> str:
        with connection.cursor() as cursor:
            cursor.execute("SHOW server_version")
            versao = cursor.fetchone()[0]
        if int(versao.split(".")[0]) < 13:
            raise Falha(f"Postgres {versao}; o projeto assume 13 ou mais novo.")
        return f"Postgres {versao}"

    def _icu(self) -> str:
        """
        O risco de verdade das collations — e não as extensões.

        `accounts/0001_initial` cria uma collation ICU não-determinística
        (`und-u-ks-level2`) e a coluna `users.email` a referencia. Sem ICU no
        build do Postgres essa migration não sobe, e o login case-insensitive
        vai junto.
        """
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM pg_collation WHERE collprovider = 'i'")
            if cursor.fetchone()[0] == 0:
                raise Falha(
                    "nenhuma collation com provider ICU. O build do Postgres "
                    "nao tem ICU, e accounts.0001 nao vai subir."
                )

            # Estar disponível não basta: o que a migration faz é CRIAR uma.
            with transaction.atomic():
                cursor.execute(
                    "CREATE COLLATION preflight_icu "
                    "(provider = icu, locale = 'und-u-ks-level2', "
                    "deterministic = false)"
                )
                transaction.set_rollback(True)
        return "collation ICU nao-deterministica pode ser criada"

    def _create_role(self) -> str:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT rolsuper, rolcreaterole FROM pg_roles "
                "WHERE rolname = current_user"
            )
            superusuario, cria_papel = cursor.fetchone()

            if not (superusuario or cria_papel):
                raise Falha(
                    "o usuario do DATABASE_URL nao e superusuario nem tem "
                    "CREATEROLE. `core.0001_rls_policies` faz CREATE ROLE e vai "
                    "falhar. Saidas: pedir o papel ao suporte da plataforma, ou "
                    "outro provedor de banco."
                )

            with transaction.atomic():
                cursor.execute(f"CREATE ROLE {ROLE_DE_TESTE} NOLOGIN NOSUPERUSER")
                transaction.set_rollback(True)

        atributo = "superusuario" if superusuario else "CREATEROLE"
        return f"usuario atual tem {atributo}; CREATE ROLE funcionou"

    def _grant_role(self) -> str:
        """
        A migration não só cria o papel — ela faz `GRANT remind_app TO
        current_user`, senão o runtime não consegue `SET ROLE`. Superusuário
        dispensa; dono comum, não.
        """
        with connection.cursor() as cursor, transaction.atomic():
            cursor.execute(f"CREATE ROLE {ROLE_DE_TESTE} NOLOGIN NOSUPERUSER")
            cursor.execute(f"GRANT {ROLE_DE_TESTE} TO CURRENT_USER")
            cursor.execute(f"SET ROLE {ROLE_DE_TESTE}")
            cursor.execute("RESET ROLE")
            transaction.set_rollback(True)
        return "GRANT e SET ROLE funcionaram"

    def _row_level_security(self) -> str:
        with connection.cursor() as cursor, transaction.atomic():
            cursor.execute("CREATE TABLE preflight_rls (id int, dono uuid)")
            cursor.execute("ALTER TABLE preflight_rls ENABLE ROW LEVEL SECURITY")
            cursor.execute(
                "CREATE POLICY preflight_dono ON preflight_rls USING "
                "(dono = NULLIF(current_setting('app.user_id', true), '')::uuid)"
            )
            # A GUC personalizada é o mecanismo de `core/rls.py`. Se a
            # plataforma restringir `SET LOCAL` de parâmetro customizado, o
            # isolamento inteiro cai — e isso não aparece em teste local nenhum.
            alvo = "00000000-0000-0000-0000-000000000000"
            cursor.execute(f"SET LOCAL app.user_id = '{alvo}'")
            cursor.execute("SELECT current_setting('app.user_id', true)")
            if cursor.fetchone()[0] != alvo:
                raise Falha("SET LOCAL de GUC personalizada nao teve efeito.")
            transaction.set_rollback(True)
        return "ENABLE RLS, CREATE POLICY e SET LOCAL de GUC funcionaram"

    def _extensao_disponivel(self, nome: str) -> bool:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM pg_available_extensions WHERE name = %s", [nome]
            )
            return cursor.fetchone() is not None
