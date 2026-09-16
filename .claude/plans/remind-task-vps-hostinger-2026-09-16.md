# Plan: remind-task — Deploy em VPS Hostinger (saindo do Railway)

**Date:** 2026-09-16
**Status:** Phases 0-5 (código) implementadas e verificadas em 2026-09-16 —
build real, stack de produção no ar localmente, health/CORS/cookie/RLS
confirmados. Branch: `feat/deploy-vps-hostinger`. Falta só o que exige
infraestrutura real (VPS, domínio, secrets do GitHub) — ver **Correções
achadas na implementação** abaixo e a Phase 6.
**Plano irmão:** [`remind-task-producao-2026-08-21.md`](remind-task-producao-2026-08-21.md)
(Railway, concluído — este plano não o revoga; a Phase 6 decide se o Railway
é desligado ou mantido em paralelo).

### Correções achadas na implementação (2026-09-16)

Duas coisas que o plano não previu, achadas rodando a stack de verdade:

1. **`env_file:` não propaga os defaults de interpolação do compose.**
   `POSTGRES_DB`/`POSTGRES_USER` tinham default `remind` só para montar o
   serviço `db` (`${POSTGRES_DB:-remind}` no `docker-compose.prod.yml`) — o
   container do `web` recebia só o que está *literalmente* escrito em
   `.env.prod`, e sem essas duas chaves `decouple` derruba o boot com
   `POSTGRES_DB not found`. Medido subindo a stack com só `POSTGRES_PASSWORD`
   declarado. Corrigido com um bloco `environment:` explícito no anchor
   `x-django`, repetindo os mesmos defaults e fixando `POSTGRES_HOST=db`.
2. **A Decisão 1 do Phase 0 (`CORS_ALLOWED_ORIGINS` deixa de ser necessário em
   same-origin) estava errada.** `config/validacao.py` recusa o boot com a
   lista vazia sem excecionar o caso same-origin — a guarda não distingue os
   dois. Correção: `.env.prod.example` declara
   `CORS_ALLOWED_ORIGINS=https://app.exemplo.com` (mesmo domínio do
   `ALLOWED_HOSTS`), que satisfaz a guarda mesmo sendo inerte em runtime
   (o browser nunca manda `Origin` em requisição same-origin).
3. **`docker/backup.sh`/`docker/restore.sh` chamam `docker compose` sem
   `-f`.** Sem ajuda, resolvem para `docker-compose.yml` (dev) — que não está
   no ar na VPS. `COMPOSE_FILE=docker-compose.prod.yml` no ambiente resolve
   sem mudar os scripts (é a variável que o próprio Compose lê); medido
   funcionando (`backup.sh` gerou dump de 574 bytes contra o `db` do
   `docker-compose.prod.yml` de teste). Documentado no README e na Phase 5.

Confirmado por medição, não suposição: `docker compose -f
docker-compose.prod.yml build` (com `base.lock`, sem pytest/ruff na imagem),
stack no ar com todos os serviços saudáveis, `curl .../api/health/` → `{"status":"ok"}`,
fallback de SPA → 200, `check --deploy --fail-level WARNING` limpo com chave
forte, e `AUTH_COOKIE_SAMESITE=Lax` + `ATOMIC_REQUESTS=True` confirmados via
shell dentro do container `web`.

## Estado atual (medido em 2026-09-16, não presumido)

A aplicação já está 100% no ar no Railway, com todas as 11 phases do plano
irmão concluídas: gunicorn + WhiteNoise, HTTPS/HSTS, throttling, e-mail via
Anymail/Brevo (HTTP, não SMTP), busca, backup/restore testado, observabilidade,
recuperação de senha e exclusão de conta. Isso importa aqui porque **a maior
parte do trabalho de "produção" já está feita e é portável** — o que falta é
só o que é específico da plataforma Railway.

Acoplamentos medidos com Railway, que este plano precisa desfazer ou substituir:

| Onde | O quê | Por quê existe |
|---|---|---|
| `docker/entrypoint.sh:43` | `gunicorn --bind "[::]:${PORT}"` | rede interna do Railway é IPv6-only |
| `config/settings/base.py:37-39` | `RAILWAY_PUBLIC_DOMAIN` entra em `ALLOWED_HOSTS` sozinho | domínio dinâmico por deploy |
| `config/settings/base.py:65-67` | `RAILWAY_HEALTHCHECK_HOST` fixo em `ALLOWED_HOSTS` | healthcheck da plataforma bate com esse Host header |
| `config/settings/prod.py:109` | `AUTH_COOKIE_SAMESITE` default `"None"` | dois serviços em domínios `*.up.railway.app` **diferentes** (Decisão 1 do plano irmão) |
| `config/settings/prod.py:184` | fallback de `SENTRY_ENVIRONMENT` em `RAILWAY_ENVIRONMENT_NAME` | rótulo automático do painel |
| `config/settings/prod.py:8-28` | `SECURE_REDIRECT_EXEMPT` para o healthcheck | ele bate em HTTP puro, sem `X-Forwarded-Proto` |
| `.railway/railway.ts`, `.env.prod.example` (comentários) | IaC e variáveis Railway-specific | topologia de 6 serviços gerenciados |
| deploy | push para `main` → Railway observa o branch e implanta sozinho | não existe em VPS — precisa de mecanismo próprio |
| `cron-alertas` (serviço Railway) + `sh -c` wrapper | Railway roda o Start Command em exec form, sem shell | não existe em VPS — usar `beat` (celery), que já está no `docker-compose.yml` de dev e nunca foi usado em produção por custo |

O que **não** precisa mudar, porque já é genérico (medido, não suposto):

- `DATABASE_URL` via `dj_database_url` já é a fonte primária (`base.py:146-165`),
  com fallback para `POSTGRES_*` — funciona igual com Postgres em container na
  VPS.
- `docker/backup.sh` e `docker/restore.sh` já aceitam `DATABASE_URL` remoto e
  não têm nada Railway-specific.
- `EMAIL_BACKEND` (Anymail/Brevo) fala HTTPS, não SMTP — o motivo de existir
  (Railway bloqueia SMTP de saída) não se aplica a uma VPS, mas trocar de volta
  para SMTP puro é trabalho novo sem necessidade. Fica como está.
- `Dockerfile` (backend) e `frontend/Dockerfile` (multi-estágio `dev`/`producao`)
  não têm nada específico do Railway — a imagem de produção do frontend já
  existe e faz fallback de SPA.
- Lockfiles com hash, RLS, throttling, health checks, observabilidade — tudo
  isso é característica da aplicação, não da plataforma.

## Goal

Ter um caminho de deploy completo e documentado para uma VPS Hostinger:
domínio próprio com HTTPS, todos os serviços em Docker Compose, deploy
repetível (não manual e não mágico), e os dois pontos que travam sem
correção — bind IPv4/IPv6 e a topologia de cookie/CORS — resolvidos antes do
primeiro `docker compose up`.

## Scope

### In-Scope

- Generalizar `entrypoint.sh` e as settings para não dependerem de env vars
  do Railway (com fallback seguro quando ausentes — nada quebra em quem ainda
  roda no Railway).
- `docker-compose.prod.yml`: `web`, `worker`, `beat` (substitui o
  `cron-alertas`), `frontend` (target `producao`), `db` e `redis` próprios,
  sem porta exposta ao host além do necessário.
- Nginx de borda (no host, via `apt`) + Certbot para TLS, em **um domínio
  só** — recomendação da Decisão 1 abaixo — reverse-proxy para `web` e para
  `frontend`.
- Mecanismo de deploy: script versionado (`docker/deploy.sh`) rodado por SSH,
  mais um workflow do GitHub Actions que dispara esse script depois do CI
  verde em push para `main`.
- `.env.prod.example` com a seção Railway substituída pela seção VPS.
- Backup agendado via `cron` do próprio host (`docker/backup.sh` já serve) e
  um ensaio de restore na VPS.
- README: seção "Deploy na VPS Hostinger" ao lado da seção Railway existente.

### Out-of-Scope

- **Desligar o Railway.** A Phase 6 decide se o Railway some ou fica como
  ambiente de fallback; não é decisão para tomar sem o VPS provado no ar.
- Trocar o provedor de e-mail (Anymail/Brevo continua).
- Orquestração além de Docker Compose (Kubernetes, Swarm, Nomad).
- Múltiplas VPS, load balancer, alta disponibilidade — uma VPS Hostinger é um
  único ponto de falha por definição; isso é aceito, não resolvido aqui.
- Migrar o banco de dados do Railway para a VPS — é o `docker/restore.sh`
  contra um dump real, mas o *momento* do corte de tráfego é decisão de
  produto (Phase 6), não uma phase de código.
- Provisionar a VPS em si (comprar, instalar Ubuntu, criar usuário SSH) — a
  Phase 0 assume que isso já foi feito manualmente por quem opera; é ação
  fora do repositório.

---

## Phases

### Phase 0 — Duas decisões que mudam o formato do trabalho

**Objective:** fixar topologia de domínio e forma do banco antes de escrever
compose ou settings — exatamente o erro que o plano irmão cometeu (duas
decisões incompatíveis descobertas só na Phase 5 dele).

**Decisão 1 — domínio e cookie.** Recomendação: **um domínio só**
(`app.exemplo.com`), com o Nginx de borda fazendo reverse-proxy de `/api/` para
o container `web` e do resto para o container `frontend`. Same-origin de
verdade: `AUTH_COOKIE_SAMESITE=Lax` funciona sem ressalva. **Correção achada na
implementação:** `CORS_ALLOWED_ORIGINS` continua *obrigatório* mesmo
same-origin — `config/validacao.py` recusa o boot com a lista vazia sem
excecionar esse caso. Declarar o mesmo domínio (`https://app.exemplo.com`)
satisfaz a guarda; fica inerte em runtime porque o browser nunca manda
`Origin` em requisição same-origin. `CSRF_TRUSTED_ORIGINS` continua sendo
derivado de `ALLOWED_HOSTS` (`prod.py:97-99`, já existe). É o caminho que o
plano irmão listou como
alternativa e não escolheu por causa da topologia forçada do Railway — aqui a
VPS não força nada, então o caminho mais simples fica disponível.

| Caminho | Custo |
|---|---|
| Um domínio, Nginx de borda roteando por path (**recomendado**) | `SameSite=Lax`; sem CORS; um Nginx a mais para configurar e renovar certificado |
| Dois subdomínios (`app.` e `api.`) | mesmo registrable domain → `Lax` também funciona; exige dois `server_name` e DNS extra, sem ganho correspondente aqui |
| `SameSite=None` (herdar o que o Railway usa) | funciona, mas é a política mais frouxa sem necessidade — a VPS não tem a restrição que o exigiu |

**Decisão 2 — banco e cache.** Recomendação: **Postgres e Redis em container
na própria VPS**, com volume nomeado e sem porta publicada para a internet
(`ports:` só em `127.0.0.1:...` ou removido do `docker-compose.prod.yml`).
Alternativa — Postgres gerenciado da Hostinger, se existir no plano contratado
— fica fora deste plano: mudaria a Phase 2 para usar `DATABASE_URL` externo em
vez de serviço `db`, e é reversível depois sem custo (a app já lê
`DATABASE_URL` de onde vier).

**Files Touched:** este arquivo (registrar a decisão tomada no **Status**).
**Verify:** o cabeçalho **Status** nomeia a topologia de domínio e a forma do
banco escolhidas.
**Done When:** as duas linhas de decisão estão escritas, e as phases 1-4
podem referenciá-las sem ambiguidade.

**Replanning triggers:**
- Se a Hostinger não permitir abrir porta 80/443 no plano contratado (raro,
  mas VPS de entrada às vezes limita) — reavaliar antes da Phase 3.

---

### Phase 1 — Settings e entrypoint sem travas do Railway

**Objective:** o mesmo código sobe em qualquer host Linux com Docker, Railway
incluso — nada aqui pode regredir o ambiente atual.

- `docker/entrypoint.sh`: bind configurável, com o mesmo default de hoje.
  `--bind "${GUNICORN_BIND:-[::]}:${PORT:-8000}"` — `[::]` continua sendo o
  default (cobre IPv4 mapeado no Linux, como já documentado no arquivo), mas
  fica com uma saída se a VPS tiver IPv6 desabilitado: `GUNICORN_BIND=0.0.0.0`.
- `config/settings/base.py`: `RAILWAY_PUBLIC_DOMAIN` e `RAILWAY_HEALTHCHECK_HOST`
  continuam existindo tal como estão — são `config(..., default="")`, então em
  uma VPS sem essas env vars eles não fazem nada. **Não tocar** — é reuso, não
  precisa de código novo. Confirmar isso é o item de verificação desta phase,
  não uma mudança.
- `config/settings/prod.py:109`: `AUTH_COOKIE_SAMESITE` continua lendo do
  ambiente com default `"None"` — a VPS declara `AUTH_COOKIE_SAMESITE=Lax` no
  `.env.prod` (Decisão 1). Nenhuma linha de código muda; é configuração.
- `config/settings/prod.py:184`: o fallback em `RAILWAY_ENVIRONMENT_NAME` fica
  como está (mesma lógica do bind) — sem essa env var, cai direto em
  `"producao"`. Verificar, não reescrever.
- `.env.prod.example`: nova seção "VPS Hostinger" ao lado da seção Railway
  existente, com os valores esperados para a Decisão 1
  (`AUTH_COOKIE_SAMESITE=Lax`, `DJANGO_ALLOWED_HOSTS=app.exemplo.com`, sem
  `CORS_ALLOWED_ORIGINS`).

**Files Touched:**
`docker/entrypoint.sh` · `.env.prod.example` · `tests/security/test_cookie_policy.py`
(caso novo: `SameSite=Lax` + `Secure=True` é combinação válida, não deveria
levantar `ImproperlyConfigured`)

**Verify:**
```bash
docker compose exec -T web pytest tests/security/test_cookie_policy.py tests/security/test_transport.py -q
docker compose build web && docker compose up -d --wait web
docker compose exec -T web env AUTH_COOKIE_SAMESITE=Lax DJANGO_SETTINGS_MODULE=config.settings.prod \
  DJANGO_SECRET_KEY=x DJANGO_ALLOWED_HOSTS=app.exemplo.com DATABASE_URL=postgres://remind:remind@db:5432/remind \
  python -c "import django; django.setup()"   # não deve levantar ImproperlyConfigured
```
**Done When:** a suíte de segurança passa com `SameSite=Lax`, e a app ainda
sobe normalmente sem nenhuma env var do Railway definida.

**Replanning triggers:**
- Se algum teste hoje assumir `AUTH_COOKIE_SAMESITE=None` como único caminho
  válido em produção, ele precisa de ajuste aqui, não depois.

---

### Phase 2 — `docker-compose.prod.yml`

**Objective:** subir os quatro serviços da aplicação na VPS com a mesma
imagem que o CI já testa.

- Novo arquivo, não uma flag no `docker-compose.yml` de dev: os dois têm
  propósitos incompatíveis (bind mount de código vs. imagem imutável; `db`/
  `redis` com porta pro host vs. sem porta nenhuma).
- `web`: usa `docker/entrypoint.sh` (sem `command:` sobrescrito, ao contrário
  do compose de dev) — `EXPOSE 8000`, publicado só em `127.0.0.1:8000` (o
  Nginx de borda, na Phase 3, é quem fala com a internet).
- `worker`: `celery -A config worker -l info`, igual ao dev.
- `beat`: `celery -A config beat -l info` — **substitui** o `cron-alertas` do
  Railway. Diferença de custo aceita conscientemente: numa VPS de preço fixo,
  um processo ocioso batendo a cada 15 min não soma conta extra, então o
  argumento de custo que fez o plano irmão preferir cron não se aplica aqui —
  `beat` é mais simples que reproduzir um cron dentro de um container.
- `frontend`: `build.target: producao`, `VITE_API_URL` como build-arg fixo em
  `https://app.exemplo.com/api` (Decisão 1 — mesma origem, path `/api`),
  publicado só em `127.0.0.1:8080`.
- `db`/`redis`: sem `ports:` publicada para `0.0.0.0` — só a rede interna do
  compose. Volumes nomeados, sem bind mount de código.
- `restart: unless-stopped` em todos os serviços — sem isso, um `reboot` da
  VPS não volta com nada no ar.

**Files Touched:**
`docker-compose.prod.yml` (novo) · `.env.prod.example`

**Verify:**
```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod config -q   # valida sintaxe e interpolação
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
curl -fsS http://127.0.0.1:8000/api/health/   # {"status":"ok",...}
curl -fsS http://127.0.0.1:8080/ | grep -q '<div id="root">'
docker compose -f docker-compose.prod.yml exec -T web python manage.py check --deploy --fail-level WARNING
docker compose -f docker-compose.prod.yml down
```
**Done When:** os quatro serviços da aplicação sobem, health responde 200, e
nem `db` nem `redis` aparecem em `docker compose -f docker-compose.prod.yml ps`
com porta publicada para `0.0.0.0`.

**Replanning triggers:**
- Se a VPS contratada não tiver RAM suficiente para `web` + `worker` + `beat`
  + Postgres + Redis + Node build simultâneo — mover o build do frontend para
  fora da VPS (CI builda a imagem, `docker push` para um registry, VPS só faz
  `pull`) fica como próxima phase, não retrabalho desta.

---

### Phase 3 — Nginx de borda + TLS

**Objective:** um domínio, HTTPS de verdade, sem cookie nem CORS quebrando —
fecha a Decisão 1.

- Nginx do **host** (não containerizado) via `apt install nginx certbot
  python3-certbot-nginx` — mais simples de depurar e renovar do que nginx
  dentro de nginx, e é o caminho documentado do Certbot para VPS.
- Um `server_name app.exemplo.com`, dois `location`:
  `location /api/ { proxy_pass http://127.0.0.1:8000/api/; }` e
  `location / { proxy_pass http://127.0.0.1:8080/; }`.
  Headers obrigatórios: `X-Forwarded-Proto https` (é o que
  `SECURE_PROXY_SSL_HEADER` em `prod.py:9` espera — sem ele, todo request
  vira redirect 301 em loop) e `X-Forwarded-For $proxy_add_x_forwarded_for`.
- `certbot --nginx -d app.exemplo.com` para emitir e configurar o redirect
  HTTP→HTTPS automaticamente; renovação por timer do systemd que o pacote
  Debian/Ubuntu do certbot já instala — confirmar que está ativo, não
  recriar.
- `SECURE_REDIRECT_EXEMPT` do healthcheck (`prod.py:28`) **não se aplica
  aqui**: quem bate no healthcheck agora é o próprio Nginx de borda, que
  sempre manda `X-Forwarded-Proto https` porque o certbot configurou isso —
  então a exceção Railway-specific fica no código sem uso, inofensiva, e não
  precisa ser removida (removê-la é risco sem benefício se o Railway
  continuar rodando em paralelo).

**Files Touched:**
`docker/nginx/app.conf` (novo — versionado no repo como referência, copiado
manualmente para `/etc/nginx/sites-available/` na VPS) · `README.md`

**Verify:**
```bash
sudo nginx -t
curl -fsS https://app.exemplo.com/api/health/
curl -fsS https://app.exemplo.com/ | grep -q '<div id="root">'
curl -fsS -o /dev/null -w '%{http_code}\n' https://app.exemplo.com/tabelas/abc   # 200, fallback SPA
curl -fsS -o /dev/null -w '%{http_code}\n' http://app.exemplo.com/                 # 301 -> https
```
**Done When:** os quatro checks acima passam, e o cookie de refresh sobrevive
à troca de rota depois do access token expirar (mesmo teste manual que o plano
irmão já fazia contra o Railway).

**Replanning triggers:**
- Se `certbot --nginx` falhar por causa de firewall da Hostinger bloqueando
  challenge HTTP-01 — usar DNS-01 é replanejamento, não ajuste.

---

### Phase 4 — Deploy: script + gate de CI

**Objective:** deploy repetível por comando, não por sequência de passos
manuais lembrados de memória.

- `docker/deploy.sh`, rodado **na VPS** (via SSH, não localmente): `git pull
  --ff-only`, `docker compose -f docker-compose.prod.yml build`,
  `docker compose -f docker-compose.prod.yml up -d`, seguido de
  `docker compose -f docker-compose.prod.yml exec -T web python manage.py
  check --deploy --fail-level WARNING` como gate pós-deploy — se falhar, o
  script sai não-zero sem ter trocado o tráfego de fato (o `up -d` já trocou;
  registrar isso como limitação conhecida, igual ao plano irmão fez com o
  `pos-deploy` do Railway não provar qual revisão respondeu).
- Novo job no `.github/workflows/ci.yml`, só em push para `main` e só depois
  dos jobs de teste (`needs:`), que conecta por SSH (chave em
  `secrets.VPS_SSH_KEY`, host em `vars.VPS_HOST`) e roda
  `ssh ... 'bash docker/deploy.sh'`. Mesma forma que o `pos-deploy` existente
  já usa para health-check pós-deploy — aqui o job **faz** o deploy, não só
  confere.
  **Gate:** sem os secrets/vars configurados, o job avisa e sai 0 (mesmo
  padrão do `pos-deploy` atual com `URL_PRODUCAO` ausente) — não trava o CI de
  quem ainda não configurou a VPS.
- Provisionar `VPS_SSH_KEY` e `VPS_HOST` no GitHub (Settings → Secrets and
  variables → Actions) é ação manual, fora deste plano — chave privada não
  entra no repositório em hipótese alguma.

**Files Touched:**
`docker/deploy.sh` (novo) · `.github/workflows/ci.yml` · `README.md`

**Verify:**
```bash
shellcheck docker/deploy.sh
ssh <usuario>@<vps> 'bash ~/remind-task/docker/deploy.sh'   # manual, primeira vez
# depois de secrets configurados: push em main -> Actions -> job de deploy verde
```
**Done When:** um push em `main` com CI verde chega à VPS sem comando manual;
um push com CI vermelho não chega (gate de `needs:`).

**Replanning triggers:**
- Se o repositório for privado e a chave SSH usada para `git pull` na VPS for
  diferente da chave de deploy do Actions — precisa de uma segunda chave
  (deploy key do repo) antes desta phase fechar.

---

### Phase 5 — Backup na VPS

**Objective:** o backup já testado no plano irmão continua funcionando fora
do Railway — só muda onde ele roda, não o que ele faz.

- `crontab` do usuário da VPS chamando `docker/backup.sh` (o script já lê
  `DATABASE_URL`/`DESTINO`/`RETENCAO` do ambiente — nenhuma mudança de
  código). Frequência e retenção: mesma do plano irmão, a menos que o volume
  de dados justifique outra.
  **Achado na implementação:** o script chama `docker compose` sem `-f`, e sem
  ajuda resolve para `docker-compose.yml` (dev) — que não está no ar na VPS.
  `COMPOSE_FILE=docker-compose.prod.yml` no ambiente resolve sem tocar no
  script (é a variável que o próprio Compose lê); no `crontab` precisa estar
  na própria linha, porque `cron` não carrega shell profile.
- Destino do arquivo **fora da própria VPS** — copiar para outro lugar (outro
  storage, outra máquina) é o que faz o backup sobreviver a "a VPS morreu",
  que é exatamente o cenário que este backup existe para cobrir (o Railway já
  tinha snapshot da plataforma; a VPS não tem nada equivalente por padrão).
- `docker/restore.sh --ensaio` rodado uma vez na própria VPS, como prova.

**Files Touched:**
`README.md` (seção de backup, crontab documentado)

**Verify:**
```bash
export COMPOSE_FILE=docker-compose.prod.yml
sh docker/backup.sh              # roda contra o compose de produção da VPS
sh docker/restore.sh --ensaio     # mesmo ensaio do plano irmão, agora aqui
crontab -l | grep backup.sh       # confirma agendamento, com COMPOSE_FILE na linha
```
**Done When:** existe um backup fora da VPS com menos de 24h de idade, e o
ensaio de restore saiu com `rc=0`.

**Replanning triggers:**
- Nenhum esperado — este é reuso direto do que a Phase 8 do plano irmão já
  provou.

---

### Phase 6 — Corte de tráfego e decisão sobre o Railway

**Objective:** decidir, com o VPS provado no ar, se o Railway sai ou fica.

**Explicitamente fora do escopo de código** — esta phase é operação e
decisão, não patch:

- Apontar o DNS do domínio de produção para a VPS (hoje aponta para o
  Railway, se houver domínio próprio; se hoje é só `*.up.railway.app`, este é
  o primeiro domínio próprio do projeto).
- Restaurar o backup de produção mais recente do Railway na VPS
  (`docker/restore.sh`, contra um dump real, não o ensaio).
- Decidir: manter o Railway como ambiente de fallback por um período, ou
  desligar os serviços. Isso tem custo mensal dos dois lados durante a
  transição — decisão de quem opera, não deste plano.

**Files Touched:** `README.md` (registrar a decisão final e a data do corte).
**Verify:** `curl -fsS https://app.exemplo.com/api/health/ready/` respondendo
`ok` a partir do domínio de produção real, com dados restaurados confirmados
por contagem de linhas (mesmo padrão de prova do restore da Phase 8 do plano
irmão).
**Done When:** o domínio de produção responde da VPS, e a decisão sobre o
Railway está escrita no README com data.

**Replanning triggers:**
- Esta phase só começa depois que as Phases 1-5 estiverem verificadas de
  ponta a ponta — não é para ser tentada em paralelo com elas.

---

## Dependencies & Assumptions

- **Assume que a VPS já existe e tem Docker + Docker Compose instalados**, com
  acesso SSH por chave. Provisionar isso é ação manual fora deste repositório
  (Hostinger entrega Ubuntu; `curl -fsSL https://get.docker.com | sh` é o
  caminho oficial, mas rodar isso é decisão de quem tem acesso à VPS).
- **Assume domínio próprio disponível** para apontar à VPS (Decisão 1, Phase 0).
  Sem domínio, TLS via Certbot HTTP-01 não funciona contra IP puro — isto
  bloquearia a Phase 3 e precisaria de replanejamento.
- Depende do plano irmão (Railway) só como referência de comportamento já
  correto — nenhuma phase deste plano reabre trabalho de lá.

## Notes

- Este plano deliberadamente **não** reescreve nada que já funciona
  (backup/restore, e-mail, RLS, throttling, observabilidade) — é troca de
  plataforma de execução, não retrabalho de produto.
- A Decisão 1 (domínio único, `Lax`) é o oposto da Decisão 1 do plano irmão
  (`*.up.railway.app`, `None`) — não é inconsistência entre os planos, é a
  mesma pergunta com uma restrição de plataforma diferente. Fica registrado
  para quem comparar os dois arquivos não achar contradição onde há só
  contexto diferente.
