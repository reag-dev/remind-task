#!/bin/sh
# Entrypoint de produção: migra e serve.
#
# `set -eu` é o que torna isto seguro: se o `migrate` falhar, o container morre
# em vez de subir um processo servindo requests contra um schema desatualizado —
# que é a falha cara, porque parece funcionar até o primeiro request tocar a
# coluna que não existe.
set -eu

python manage.py migrate --noinput

# ⚠️ Uma réplica só. Com duas ou mais, duas cópias do `migrate` correm juntas no
# deploy; o lock do Postgres serializa as migrations, mas nada garante que a
# segunda não veja um estado parcial. Ao escalar `web`, o migrate sai daqui e
# vira release command da plataforma — está registrado na Phase 3 do plano.
#
# `exec` faz o gunicorn virar o PID 1: sem ele, o shell fica no meio e o
# SIGTERM do deploy não chega aos workers, que só morrem no timeout.
exec gunicorn config.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers "${GUNICORN_WORKERS:-3}" \
    --access-logfile - \
    --error-logfile -
