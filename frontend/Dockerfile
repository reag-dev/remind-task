# Dois alvos, um arquivo:
#
#   --target dev       servidor do Vite com HMR (o que o compose usa)
#   --target producao  `dist/` servido por nginx (o que vai para o Railway)
#
# `producao` é o último estágio, então um `docker build` sem `--target` produz a
# imagem de produção. O compose pede `target: dev` explicitamente — se algum dia
# essa linha sumir, o sintoma é um container de nginx onde se esperava HMR.
#
# O CONTEXTO É A RAIZ DO REPOSITÓRIO, não `frontend/`. Isso existe para alcançar
# `docker/certs/`, o mesmo diretório de CAs que o Dockerfile do backend usa.
# Duplicar os certificados dentro de `frontend/` daria dois lugares para
# atualizar e um para esquecer.
FROM node:22-slim AS base

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

# ------------------------------------------------------------------ dev

FROM base AS dev

# Casa com `server.port` do vite.config.ts e com CORS_ALLOWED_ORIGINS do backend.
EXPOSE 3000

# `--host` publica em 0.0.0.0. O padrão do Vite escuta só em localhost, que
# dentro do container significa "o próprio container" — a porta apareceria
# publicada e recusaria conexão do host.
CMD ["npm", "run", "dev", "--", "--host"]

# ---------------------------------------------------------------- build

FROM base AS build

# O Vite resolve `import.meta.env` em tempo de COMPILAÇÃO, não de execução.
#
# A consequência precisa ficar dita: **a imagem do frontend é específica do
# ambiente**. Não existe "promover a mesma imagem de staging para produção" —
# ela sairia apontando para a API de staging, e o sintoma seria um app que
# carrega bem e fala com o backend errado.
ARG VITE_API_URL

# Sem a URL, `import.meta.env.VITE_API_URL` compila como `undefined` e cada
# chamada vira uma request para `undefined/tabelas/`. O build passa, a imagem
# sobe, e a falha só aparece no browser do usuário. Quebrar aqui é mais barato.
RUN test -n "$VITE_API_URL" || {         echo "ERRO: --build-arg VITE_API_URL=... é obrigatório no alvo producao." >&2;         exit 1;     }

ENV VITE_API_URL=$VITE_API_URL

# `tsc -b && vite build` — o typecheck faz parte do build de propósito: um erro
# de tipo deve derrubar a imagem, não virar um `any` implícito em produção.
RUN npm run build

# ------------------------------------------------------------- producao

FROM nginx:1.27-alpine AS producao

# Default para uso local (`docker run -p 8080:80`). No Railway a plataforma
# injeta PORT e o template escuta nela — ver frontend/nginx.conf.template.
ENV PORT=80

# `templates/`, não `conf.d/`: a entrypoint da imagem oficial roda envsubst
# sobre este arquivo no start e escreve o resultado em conf.d/. Copiar direto
# para conf.d/ pularia a substituição, e o nginx morreria em `listen ${PORT};`.
COPY frontend/nginx.conf.template /etc/nginx/templates/default.conf.template

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
