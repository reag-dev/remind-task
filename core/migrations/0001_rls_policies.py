"""
Row-Level Security (RS01).

Cria o papel de runtime `remind_app` e liga as policies de dono nas cinco
tabelas de domínio. A explicação de como o runtime entra nesse papel está em
`core/rls.py`; aqui fica só o DDL.

Nota sobre `FORCE ROW LEVEL SECURITY`: sem ele o DONO da tabela ignora as
policies em silêncio. Com ele, um `migrate` futuro que mexa em LINHAS (uma data
migration) rodando como dono não-superusuário também será filtrado — se isso
acontecer, a migration precisa de `SET LOCAL row_security = off` explícito, o
que é justamente o tipo de decisão que deve ser consciente e não acidental.
"""

from django.db import migrations

ROLE = "remind_app"

# Tabelas com coluna `user_id` própria (desnormalizada de propósito — nota 1 do
# modelo de dados). A policy é uma comparação direta, sem subquery.
OWNED_TABLES = ("tables", "records", "alert_rules", "alerts")

# `columns` não tem dono próprio: pertence à tabela, que tem. A policy vai por
# EXISTS. Duplicar `user_id` aqui traria a mesma desnormalização sem nenhum
# ganho de leitura — colunas nunca são consultadas fora do contexto da tabela.
CURRENT_USER = "NULLIF(current_setting('app.user_id', true), '')::uuid"

SETUP_ROLE = f"""
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') THEN
        -- NOLOGIN: não é uma credencial. A conexão do Django entra neste papel
        -- com SET LOCAL ROLE e sai no fim da transação — não há senha nova para
        -- rotacionar, distribuir ou vazar.
        CREATE ROLE {ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE INHERIT;
    END IF;
END
$$;

-- O papel de login precisa ser membro de {ROLE} para poder SET ROLE nele.
-- Superusuário já poderia; para o dono comum de produção, isto é obrigatório.
DO $$
BEGIN
    EXECUTE format('GRANT {ROLE} TO %I', current_user);
END
$$;

GRANT USAGE ON SCHEMA public TO {ROLE};

-- Antes do GRANT em massa: assim as tabelas que MIGRATIONS POSTERIORES criarem
-- (django_session, axes_*, token_blacklist_*, o que vier depois) já nascem com
-- permissão. Sem isto, cada app novo quebraria o runtime até alguém lembrar.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {ROLE};
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO {ROLE};

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {ROLE};
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {ROLE};
"""

TEARDOWN_ROLE = f"""
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {ROLE};
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE USAGE, SELECT ON SEQUENCES FROM {ROLE};
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {ROLE};
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {ROLE};
REVOKE USAGE ON SCHEMA public FROM {ROLE};
-- O papel NÃO é derrubado: ele é do cluster, não do banco. O banco de teste e o
-- de desenvolvimento compartilham o mesmo, e um DROP ROLE aqui derrubaria o
-- outro. Remover o papel é operação manual de DBA.
"""


def _enable(table: str, using: str) -> str:
    return f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
CREATE POLICY {table}_owner ON {table}
    USING ({using})
    WITH CHECK ({using});
"""


def _disable(table: str) -> str:
    return f"""
DROP POLICY IF EXISTS {table}_owner ON {table};
ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
"""


POLICIES = "".join(
    _enable(table, f"user_id = {CURRENT_USER}") for table in OWNED_TABLES
) + _enable(
    "columns",
    f"EXISTS (SELECT 1 FROM tables t WHERE t.id = columns.table_id "
    f"AND t.user_id = {CURRENT_USER})",
)

DROP_POLICIES = "".join(_disable(table) for table in (*OWNED_TABLES, "columns"))


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("accounts", "0001_initial"),
        ("tables", "0001_initial"),
        ("records", "0003_alter_record_table"),
        ("alerts", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(sql=SETUP_ROLE, reverse_sql=TEARDOWN_ROLE),
        migrations.RunSQL(sql=POLICIES, reverse_sql=DROP_POLICIES),
    ]
