#!/bin/sh
# Entrypoint de produção: migra e serve.
#
# `set -eu` é o que torna isto seguro: se o `migrate` falhar, o container morre
# em vez de subir um processo servindo requests contra um schema desatualizado —
# que é a falha cara, porque parece funcionar até o primeiro request tocar a
# coluna que não existe.
set -eu

# `manage.py`, `wsgi.py` e `celery.py` usam `os.environ.setdefault(...,
# "config.settings.dev")`. Esquecer a variável na plataforma nao daria erro
# nenhum: o container subiria com DEBUG=True, cookie sem Secure, sem HSTS e com
# a browsable API aberta — a falha exatamente do tipo que este entrypoint
# existe para tornar impossivel. Producao e o default de quem roda por aqui.
#
# O compose nunca chega nesta linha (cada servico sobrescreve `command:`), e
# ainda define a variavel explicitamente no `.env`.
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.prod}"

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
