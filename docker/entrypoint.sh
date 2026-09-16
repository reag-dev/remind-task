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
#
# `[::]` e NÃO `0.0.0.0` por default, e isso não é detalhe de estilo.
#
# A rede interna do Railway é IPv6, e é por ela que o edge e o healthcheck
# alcançam o container. Escutando em `0.0.0.0` — que é IPv4 puro — não há nada
# no endereço que a plataforma procura: a conexão nunca se estabelece. O sintoma
# é cruel de diagnosticar porque a aplicação sobe perfeitamente, sem um erro
# sequer no log, e o domínio responde `502 Application failed to respond` — o
# log fica limpo justamente porque requisição nenhuma chega até ele.
#
# `[::]` cobre os dois na maioria dos hosts Linux: com o `net.ipv6.bindv6only=0`
# que é o padrão, um socket IPv6 aceita também conexão IPv4 mapeada. Por isso a
# porta continua alcançável pelo compose e pelo CI, que falam IPv4.
#
# `GUNICORN_BIND` é a válvula de escape para quem não está no Railway: uma VPS
# com IPv6 desabilitado no host (comum em provedores de entrada) não teria
# nada escutando em `[::]`, e o sintoma seria o mesmo 502 silencioso. Nesse
# caso, `GUNICORN_BIND=0.0.0.0` no `.env` resolve sem tocar neste arquivo.
exec gunicorn config.wsgi:application \
    --bind "${GUNICORN_BIND:-[::]}:${PORT:-8000}" \
    --workers "${GUNICORN_WORKERS:-3}" \
    --access-logfile - \
    --error-logfile -
