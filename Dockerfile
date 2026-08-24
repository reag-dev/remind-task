FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # pip valida TLS contra o bundle embutido do certifi, que ignora o trust store
    # do sistema. Apontar para o store do SO faz ele enxergar as CAs adicionadas
    # abaixo — necessário atrás de proxy/antivírus com inspeção TLS.
    # A verificação continua LIGADA; só a lista de raízes confiáveis muda.
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

WORKDIR /app

# Sem build-essential/libpq-dev de proposito: todas as deps de requirements/
# distribuem wheel para cp312 (psycopg[binary] e argon2-cffi inclusive), entao
# nada compila do source. Se algum dia uma dep so tiver sdist, o build quebra
# aqui — a correcao e um estagio de build separado, nao inchar a imagem final.
# curl e usado pelo healthcheck do docker-compose.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# CAs locais opcionais. Vazio na maioria das máquinas — ver docker/certs/README.md.
COPY docker/certs/ /usr/local/share/ca-certificates/
RUN update-ca-certificates

# dev.txt por padrao para o compose (a suite roda dentro do container); a
# imagem de producao passa `--build-arg REQUIREMENTS=base.txt` e nao carrega
# pytest, ruff nem factory-boy.
ARG REQUIREMENTS=dev.txt

COPY requirements/ requirements/
RUN pip install --upgrade pip && pip install -r "requirements/${REQUIREMENTS}"

COPY . .

# O bit de execucao nao sobrevive de forma confiavel a um working copy Windows,
# e a falha e opaca ("exec format error" / "permission denied" no start).
RUN chmod +x /app/docker/entrypoint.sh

# collectstatic no BUILD, nao no start: o start ja paga o migrate, e um
# ManifestStaticFilesStorage com arquivo faltando deve quebrar aqui — onde o
# deploy ainda nao trocou o trafego — e nao no primeiro request.
#
# As variaveis abaixo existem so para o modulo de settings importar: base.py
# exige SECRET_KEY e credencial de banco sem default, de proposito. Nada aqui
# toca o banco nem entra na imagem final como configuracao — sao locais do RUN,
# e o processo em producao recebe os valores reais do ambiente da plataforma.
RUN DJANGO_SETTINGS_MODULE=config.settings.prod \
    DJANGO_SECRET_KEY=build-only-nao-usada-em-runtime-xJ38fkQ2mZp9 \
    DJANGO_ALLOWED_HOSTS=build.invalid \
    CORS_ALLOWED_ORIGINS=https://build.invalid \
    DATABASE_URL=postgres://build:build@build.invalid:5432/build \
    python manage.py collectstatic --noinput

# Documental: em producao quem manda no bind e $PORT, injetado pela plataforma.
EXPOSE 8000

# CMD, nao ENTRYPOINT, e a diferenca importa: o compose sobrescreve o comando de
# `web`, `worker` e `beat` (ver `command:` em cada servico). Com ENTRYPOINT, o
# `command:` viraria *argumento* do entrypoint, que os ignora e sobe gunicorn de
# qualquer jeito — o worker do Celery viraria um segundo servidor web, calado.
CMD ["/app/docker/entrypoint.sh"]
