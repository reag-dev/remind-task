#!/bin/sh
# Restaura um backup — de verdade, ou em ensaio.
#
#   sh docker/restore.sh backups/remind-20260825-140000.sql.gz
#       APAGA o banco do compose e o recria a partir do arquivo.
#
#   sh docker/restore.sh --ensaio [arquivo]
#       Sobe um Postgres descartável, restaura ali, confere e destrói. Não
#       encosta no banco de desenvolvimento. Sem arquivo, usa o backup mais
#       recente de `backups/`.
#
# O ensaio é o ponto desta phase. Backup que nunca foi restaurado é suposição, e
# a forma de descobrir que a suposição era falsa costuma ser o dia em que ela
# precisa ser verdade.
set -eu

# ---------------------------------------------------------------- o papel
#
# `pg_dump` de um BANCO não carrega objetos de CLUSTER: papéis e quem é membro
# de quem ficam de fora. O dump traz os GRANTs para `remind_app` (são do banco),
# mas não o `CREATE ROLE` nem o `GRANT remind_app TO <dono>`.
#
# Medido em cluster limpo, sem criar o papel antes:
#
#   ERROR:  role "remind_app" does not exist
#
# e o restore aborta na seção de GRANTs — DEPOIS de já ter carregado as tabelas
# e os dados. O banco fica com todas as linhas no lugar e ZERO privilégios para
# o papel de runtime: parece restaurado, e a aplicação não lê uma linha sequer.
# É por isso que o papel é criado ANTES do dump, e não depois.
#
# O DDL é o mesmo da migration `core/0001_rls_policies` — de propósito. Os
# GRANTs em tabela não são repetidos aqui: esses o dump tem.
PAPEL_SQL='
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '"'"'remind_app'"'"') THEN
        CREATE ROLE remind_app NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE INHERIT;
    END IF;
END
$$;
DO $$
BEGIN
    EXECUTE format('"'"'GRANT remind_app TO %I'"'"', current_user);
END
$$;
'

CONFERE_SQL="
SELECT 'tabelas.......... ' || count(*) FROM information_schema.tables WHERE table_schema = 'public';
SELECT 'policies RLS..... ' || count(*) FROM pg_policies WHERE schemaname = 'public';
SELECT 'grants remind_app ' || count(*) FROM information_schema.role_table_grants WHERE grantee = 'remind_app';
SELECT 'users............ ' || count(*) FROM users;
SELECT 'tables........... ' || count(*) FROM tables;
SELECT 'records.......... ' || count(*) FROM records;
"

ultimo_backup() {
    ls -t backups/remind-*.sql.gz 2>/dev/null | head -1
}

# ------------------------------------------------------------------ ensaio

ensaio() {
    ARQUIVO="${1:-$(ultimo_backup)}"
    [ -n "$ARQUIVO" ] || { echo "ERRO: nenhum backup em backups/ — rode 'make backup'" >&2; exit 1; }
    [ -f "$ARQUIVO" ] || { echo "ERRO: $ARQUIVO não existe" >&2; exit 1; }

    # O dono vem do PRÓPRIO dump, não do `.env`: no cenário que este ensaio
    # simula — o fornecedor sumiu — o arquivo é tudo o que restou. Se o cluster
    # de destino não tiver o papel que o dump cita em `ALTER DEFAULT PRIVILEGES
    # FOR ROLE`, essas linhas falham.
    DONO="$(gunzip -c "$ARQUIVO" | grep -m1 '^ALTER DEFAULT PRIVILEGES FOR ROLE' | awk '{print $6}' || true)"
    [ -n "$DONO" ] || { echo "ERRO: não achei o papel dono no dump" >&2; exit 1; }

    IMAGEM="$(docker compose config --images db)"
    NOME="rt-ensaio-restore-$$"

    derrubar() { docker rm -f "$NOME" >/dev/null 2>&1 || true; }
    trap derrubar EXIT INT TERM

    echo "ensaio: $ARQUIVO -> cluster descartável ($IMAGEM, dono '$DONO')" >&2
    docker run --rm -d --name "$NOME" \
        -e POSTGRES_USER="$DONO" \
        -e POSTGRES_PASSWORD=ensaio \
        -e POSTGRES_DB=ensaio \
        "$IMAGEM" >/dev/null

    # Sem init.sql: as extensões (citext, pgcrypto) têm que vir do dump. Se um
    # dia não vierem, é aqui que se descobre — não no dia do desastre.
    espera=0
    until docker exec "$NOME" pg_isready -U "$DONO" -d ensaio >/dev/null 2>&1; do
        espera=$((espera + 1))
        [ "$espera" -lt 60 ] || { echo "ERRO: o cluster do ensaio não subiu" >&2; exit 1; }
        sleep 1
    done

    docker exec -i "$NOME" psql -U "$DONO" -d ensaio -v ON_ERROR_STOP=1 -q <<PAPEL
$PAPEL_SQL
PAPEL

    gunzip -c "$ARQUIVO" | docker exec -i "$NOME" psql -U "$DONO" -d ensaio -v ON_ERROR_STOP=1 -q > /dev/null

    echo "--- estado restaurado ---" >&2
    docker exec -i "$NOME" psql -U "$DONO" -d ensaio -tA <<CONFERE
$CONFERE_SQL
CONFERE

    echo "ensaio concluído sem erro — o backup restaura" >&2
}

# ------------------------------------------------------------- restore real

restore_real() {
    ARQUIVO="$1"
    [ -f "$ARQUIVO" ] || { echo "ERRO: $ARQUIVO não existe" >&2; exit 1; }

    # Destrutivo e sem volta. Exige confirmação explícita em vez de perguntar no
    # terminal: assim o comando é o mesmo rodado à mão e por um runbook, e não
    # existe a versão que "só passa Enter".
    if [ "${CONFIRMA:-}" != "sim" ]; then
        echo "ERRO: isto APAGA o banco do compose e o recria a partir de $ARQUIVO." >&2
        echo "      Se é isso mesmo:  CONFIRMA=sim make restore BACKUP=$ARQUIVO" >&2
        echo "      Para só conferir que o backup presta:  make restore-ensaio" >&2
        exit 1
    fi

    # `DATABASE_URL` definido significa banco remoto — produção. Este script não
    # aponta para lá: derrubar o banco de produção precisa de mais cerimônia que
    # uma variável de ambiente, e a que existe é o runbook do README.
    [ -z "${DATABASE_URL:-}" ] || {
        echo "ERRO: DATABASE_URL definido. Este alvo só restaura o banco local." >&2
        exit 1
    }

    echo "restaurando $ARQUIVO no banco do compose..." >&2

    # `db` de pé e `web` PARADO: o Django segura conexões, e o DROP DATABASE
    # falha enquanto existir uma. Derrubar só o web deixa o banco no ar.
    docker compose stop web worker beat >/dev/null 2>&1 || true
    docker compose up -d --wait db >/dev/null

    docker compose exec -T db sh -c '
        psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 -q \
            -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '"'"'$POSTGRES_DB'"'"' AND pid <> pg_backend_pid();" \
            -c "DROP DATABASE IF EXISTS \"$POSTGRES_DB\";" \
            -c "CREATE DATABASE \"$POSTGRES_DB\" OWNER \"$POSTGRES_USER\";"' > /dev/null

    docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -q' <<PAPEL
$PAPEL_SQL
PAPEL

    gunzip -c "$ARQUIVO" \
        | docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -q' > /dev/null

    echo "--- estado restaurado ---" >&2
    docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tA' <<CONFERE
$CONFERE_SQL
CONFERE

    docker compose up -d --wait web >/dev/null
    echo "restore concluído — web de volta" >&2
}

case "${1:---ensaio}" in
    --ensaio) ensaio "${2:-}" ;;
    -*) echo "uso: sh docker/restore.sh [--ensaio] [arquivo.sql.gz]" >&2; exit 2 ;;
    *) restore_real "$1" ;;
esac
