# Imagem de DESENVOLVIMENTO: roda o servidor do Vite com HMR, para que
# `docker compose up` suba a stack inteira sem exigir Node no host.
#
# Não serve para produção. O build de produção é `npm run build`, que emite
# estáticos para um CDN ou nginx — outro Dockerfile, quando houver deploy.
#
# O CONTEXTO É A RAIZ DO REPOSITÓRIO, não `frontend/`. Isso existe para alcançar
# `docker/certs/`, o mesmo diretório de CAs que o Dockerfile do backend usa.
# Duplicar os certificados dentro de `frontend/` daria dois lugares para
# atualizar e um para esquecer.
FROM node:22-slim

# Mesma armadilha que derruba o `pip install` do backend, com outro nome: atrás
# de antivírus ou proxy com inspeção TLS, o npm morre em
# `UNABLE_TO_VERIFY_LEAF_SIGNATURE`. O Node NÃO lê o trust store do sistema por
# conta própria — ele carrega uma lista compilada no binário —, então instalar a
# CA não basta: `NODE_EXTRA_CA_CERTS` é o que a acrescenta.
#
# A verificação continua LIGADA. `npm config set strict-ssl false` resolveria a
# mensagem e abriria a porta para pacote adulterado; ver docker/certs/README.md.
ENV NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# CAs locais opcionais. Vazio na maioria das máquinas — ver docker/certs/README.md.
COPY docker/certs/ /usr/local/share/ca-certificates/
RUN update-ca-certificates

WORKDIR /app

# package.json + lockfile antes do resto: enquanto as dependências não mudam,
# esta camada vem do cache e o `npm ci` não roda de novo a cada edição de
# código-fonte.
COPY frontend/package.json frontend/package-lock.json ./

# `ci`, não `install`: instala exatamente o que está no lockfile e falha se os
# dois discordarem, em vez de resolver versões novas em silêncio.
RUN npm ci --no-audit --no-fund

COPY frontend/ ./

# Casa com `server.port` do vite.config.ts e com CORS_ALLOWED_ORIGINS do backend.
EXPOSE 3000

# `--host` publica em 0.0.0.0. O padrão do Vite escuta só em localhost, que
# dentro do container significa "o próprio container" — a porta apareceria
# publicada e recusaria conexão do host.
CMD ["npm", "run", "dev", "--", "--host"]
