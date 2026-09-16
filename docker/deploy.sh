#!/bin/sh
# Deploy de produção na VPS. Roda NA VPS (via SSH, disparado pelo workflow do
# CI ou manualmente) — nunca no host de quem desenvolve.
#
# `set -eu` pelo mesmo motivo do entrypoint: se `git pull` ou o `build`
# falharem, o script morre antes do `up -d` trocar qualquer coisa no ar.
set -eu

cd "$(dirname "$0")/.."

# `--ff-only` recusa merge: se o histórico da VPS divergiu do remoto (alguém
# editou direto lá, por exemplo), o deploy para em vez de criar um merge
# commit silencioso num diretório que devia só espelhar o repositório.
git pull --ff-only

# Sem --env-file: o default do próprio Compose já é o arquivo `.env` neste
# diretório — mesma convenção que o `env_file: .env` do docker-compose.prod.yml
# espera. `.env` (não `.env.prod`) precisa existir aqui, copiado a partir de
# `.env.prod.example`.
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d

# Gate pós-deploy: `check --deploy` cobre configuração de segurança (headers,
# cookies, HSTS); o `migrate` já roda dentro do entrypoint do container antes
# do gunicorn subir (docker/entrypoint.sh), então não é repetido aqui.
#
# Limitação conhecida, igual à do `pos-deploy` do Railway: o `up -d` já troca
# o container ANTES deste gate rodar. Um `check --deploy` vermelho aqui avisa
# depois do fato, não impede — não há endpoint de versão para provar qual
# revisão está respondendo.
docker compose -f docker-compose.prod.yml exec -T web \
    python manage.py check --deploy --fail-level WARNING

echo "deploy concluído: $(git rev-parse --short HEAD)"
