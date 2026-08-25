#!/bin/sh
# Dump do Postgres para `backups/`, com retenção.
#
# Roda no HOST (precisa do docker), e não dentro de um container: o arquivo tem
# que sobreviver ao container que o gerou. Um backup que mora no mesmo lugar que
# o banco não é backup — é uma segunda cópia do mesmo ponto único de falha.
#
# Por que existir, se o Railway já faz snapshot do Postgres gerenciado: o
# snapshot protege contra perda de disco, não contra perder a CONTA. Apagar o
# projeto, atrasar a fatura ou o fornecedor encerrar o serviço leva o banco e os
# snapshots juntos. Este dump sai da fronteira do fornecedor.
#
# Uso:
#   sh docker/backup.sh                 # banco do compose (desenvolvimento)
#   DATABASE_URL=postgres://... sh docker/backup.sh   # banco remoto (produção)
#   RETENCAO=14 sh docker/backup.sh     # quantos arquivos manter (padrão: 7)
set -eu

DESTINO="${DESTINO:-backups}"
RETENCAO="${RETENCAO:-7}"
CARIMBO="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$DESTINO"

# `.sql` intermediário, e não `pg_dump | gzip` direto, porque em `sh` o status
# de saída de um pipe é o do ÚLTIMO comando: o gzip termina feliz comprimindo um
# dump truncado, e o script reportaria sucesso. A falha do pg_dump precisa ser
# vista antes de qualquer coisa virar arquivo.
PARCIAL="$DESTINO/.parcial-$CARIMBO.sql"
FINAL="$DESTINO/remind-$CARIMBO.sql.gz"

limpar_parcial() { rm -f "$PARCIAL"; }
trap limpar_parcial EXIT INT TERM

if [ -n "${DATABASE_URL:-}" ]; then
    echo "origem: DATABASE_URL (remoto)" >&2
    # `run --no-deps --entrypoint pg_dump` usa só o CLIENTE da imagem do
    # Postgres; nenhum servidor sobe. A imagem vem do compose de propósito —
    # assim a versão do pg_dump acompanha a do banco em um lugar só.
    docker compose run --rm --no-deps -T --entrypoint pg_dump db "$DATABASE_URL" > "$PARCIAL"
else
    echo "origem: serviço 'db' do compose" >&2
    # As credenciais já estão no ambiente do container. Lê-las do `.env` no host
    # seria uma segunda fonte de verdade, e o dia em que divergissem o backup
    # apontaria para o banco errado sem reclamar.
    docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$PARCIAL"
fi

# O pg_dump escreve esta linha por último. Sem ela o arquivo está cortado — o
# que acontece quando a conexão cai no meio, e é justamente o backup que
# ninguém percebe estar quebrado até precisar dele.
if ! tail -5 "$PARCIAL" | grep -q "PostgreSQL database dump complete"; then
    echo "ERRO: dump incompleto (marcador final ausente) — nada foi gravado" >&2
    exit 1
fi

gzip -c "$PARCIAL" > "$FINAL"
gzip -t "$FINAL"

echo "backup: $FINAL ($(wc -c < "$FINAL") bytes)" >&2

# Retenção: mantém os N mais novos. `ls -t` ordena por mtime, que é o que
# importa aqui — o nome tem carimbo, mas ordenar por nome quebraria no dia em
# que alguém renomeasse um arquivo.
sobrando="$(ls -t "$DESTINO"/remind-*.sql.gz 2>/dev/null | tail -n +"$((RETENCAO + 1))" || true)"
if [ -n "$sobrando" ]; then
    echo "$sobrando" | while read -r velho; do
        echo "retenção: removendo $velho" >&2
        rm -f "$velho"
    done
fi
