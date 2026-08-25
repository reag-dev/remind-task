# Plan: remind-task — Produção no Railway, e-mail e busca

**Date:** 2026-08-21
**Status:** Phase 0 **concluída** em 2026-08-24. Decisões registradas:

| Decisão | Escolha | Consequência |
|---|---|---|
| Topologia de domínios | **Só `*.up.railway.app`** (sem domínio próprio) | `SameSite=None; Secure` é obrigatório; CSRF explícito e CORS por origem exata entram na Phase 1 — ver *Gatilho disparado* abaixo |
| Provedor de e-mail | ~~**Resend**~~ → **SMTP do Gmail** na implantação (2026-08-24) | Ver a nota abaixo: as duas decisões eram incompatíveis |

> **⚠️ As duas decisões acima se contradiziam, e ninguém notou até a Phase 5
> implantar.** Provedor transacional exige **domínio próprio** verificado com
> SPF/DKIM; a Decisão 1 abriu mão de domínio próprio. Sem domínio, o Resend só
> entrega no endereço do dono da conta — o que não serve a usuário nenhum.
>
> A saída foi SMTP de uma conta de e-mail comum: é servidor legítimo, entrega
> para qualquer destinatário e não pede domínio. **Nenhuma linha de código
> mudou** — a aplicação fala SMTP puro e a amarração a fornecedor é só a
> credencial, que foi exatamente o critério da Decisão 2.
>
> Custo aceito: ~500 e-mails/dia, remetente pessoal em vez do produto, e
> reputação de envio misturada com a caixa pessoal de quem opera. O caminho de
> volta a um provedor transacional está em `.env.prod.example` e custa quatro
> variáveis.
>
> **A lição é sobre o formato da Phase 0, não sobre e-mail:** duas decisões
> foram tomadas na mesma tabela sem que se perguntasse se uma restringia a
> outra.

**Gatilho de replanejamento disparado pela Decisão 1.** O plano previa isto: com
dois registrable domains diferentes, o cookie de refresh só sobrevive com
`SameSite=None; Secure`. A Phase 1 cresceu para absorver o custo — CSRF
explícito, CORS por origem exata e validação no boot. Nenhuma outra phase muda.

Revisado em 2026-08-21 — nenhuma phase de implementação iniciada.
A versão anterior assumia "um host qualquer com Docker" e entregava
`docker-compose.prod.yml`. **O Railway não roda docker-compose**, então as phases
de implantação foram refeitas. Acrescentadas notificações por e-mail e busca em
colunas de texto.
**Planos irmãos:** [`remind-task-mvp-2026-08-19.md`](remind-task-mvp-2026-08-19.md) (backend, concluído) ·
[`remind-task-frontend-2026-08-20.md`](remind-task-frontend-2026-08-20.md) (frontend, concluído)

## Goal

Colocar o remind-task no ar no Railway, com HTTPS, notificação por e-mail
funcionando e busca textual nos registros.

## Estado atual (medido em 2026-08-21, não presumido)

Pronto e sem trabalho pendente: headers de produção (`check --deploy` limpo),
HTTPS/HSTS/cookies, isolamento em duas camadas, migrations sem drift, CI com 3
jobs verdes, segredos fora do repo, e `npm run build` passando (340 kB, 105 kB
gzip).

### O que falta — implantação

**Não existe caminho de deploy.** `gunicorn>=23.0` está em
`requirements/base.txt` e **não é referenciado em lugar nenhum**; o `Dockerfile`
termina em `CMD ["python", "manage.py", "runserver"]`.

**As settings não leem o que o Railway entrega.** O Railway injeta
`DATABASE_URL` e `PORT`; `config/settings/base.py` lê `POSTGRES_DB`,
`POSTGRES_USER`, `POSTGRES_HOST`… individualmente, e nada lê `PORT`. `REDIS_URL`
é a única variável que já casa.

**Estáticos não seriam servidos** (sem WhiteNoise, e `DEBUG=False` desliga o
`runserver`), e **o frontend não tem forma de produção**: `frontend/Dockerfile`
roda `npm run dev`. As 8 rotas client-side precisam de fallback para
`index.html`.

**A URL da API é embutida no bundle.** Verificado: o `dist/assets/*.js` atual
contém `http://localhost:8000/api` literal.

### ⚠️ O domínio padrão do Railway quebra o cookie de refresh

`AUTH_COOKIE_SAMESITE` é o literal `"Lax"` em `config/settings/base.py:154`.

Dois serviços no Railway recebem, por padrão, domínios como
`web-xxxx.up.railway.app` e `front-yyyy.up.railway.app`. Como `up.railway.app`
está na Public Suffix List, esses dois **são registrable domains diferentes** —
não é o caso "mesmo site" que o `Lax` permite. O cookie de refresh não seria
enviado, e a sessão morreria a cada 15 minutos, sem erro visível: o usuário
simplesmente cai para a tela de login.

O plano do frontend já registrou essa armadilha como gatilho de replanejamento.
Ela deixou de ser hipotética — é o comportamento padrão da plataforma escolhida.
A Phase 0 decide o caminho; a Phase 1 implementa.

### O que falta — segurança sob tráfego real

- **Sem throttling.** `REST_FRAMEWORK` não declara `DEFAULT_THROTTLE_CLASSES`.
  O `django-axes` cobre só o login. O export, que transmite a queryset inteira,
  é o endpoint mais caro e não tem limite.
- **O health check vaza detalhe do banco.** `core/views.py` devolve
  `{"detail": str(exc)}` num 503 `AllowAny`; a mensagem do psycopg carrega host,
  porta e usuário. Contradiz o RS05, que o projeto aplica com rigor no log.
- **Sem lockfile.** `requirements/base.txt` usa faixas; o próprio arquivo diz
  "lockfile entra quando o projeto estabilizar" — estabilizou.

### O que falta — e-mail (menos do que parece)

**O modelo já prevê o canal.** `AlertChannel.EMAIL` existe
(`alerts/models.py:15`), a constraint `alert_rules_unique` é sobre
`(table, offset_days, channel)` — então uma tabela pode ter regra in-app **e**
de e-mail para a mesma antecedência —, `AlertStatus` já tem `PENDING` e
`FAILED`, e `alerts/services.py:94` faz:

```python
delivered_immediately = rule.channel == AlertChannel.IN_APP
...
status=AlertStatus.SENT if delivered_immediately else AlertStatus.PENDING,
```

Ou seja: alertas de e-mail **já nascem `PENDING` esperando confirmação de
envio**. A costura foi desenhada e deixada aberta. Há inclusive um teste que
cria uma regra `AlertChannel.EMAIL` (`alerts/tests/test_scan_task.py:106`).

O que não existe: `grep` por `send_mail|EmailMessage|EMAIL_BACKEND|smtp` não
retorna **nada**. Falta o envio, a transição `PENDING → SENT/FAILED`, o template
e a configuração de provedor.

### O que falta — busca

Não há busca na API. `search_fields` só aparece nos `admin.py`. Os valores vivem
em `data JSONB`, e o índice existente é
`GinIndex(fields=["data"], opclasses=["jsonb_path_ops"])` — que serve para
**containment** (`@>`), e **não acelera `ILIKE`**. Busca por substring, hoje,
seria varredura sequencial.

### O que falta — conta: recuperação de senha e exclusão

Nenhuma das duas existe. `accounts/urls.py` tem `register`, `login`, `refresh`,
`logout` e `me`; `MeView` é `RetrieveUpdateAPIView` — **GET e PATCH, sem DELETE**.

Dois achados medidos que mudam como isso deve ser construído:

**1. A tabela `users` não tem policy de RLS.** As policies cobrem `tables`,
`records`, `alert_rules`, `alerts` e `columns`
(`core/migrations/0001_rls_policies.py:19`). `users` está fora — e o papel
`remind_app` recebe `GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES`.

Hoje isso é inofensivo, porque nenhum endpoint apaga usuário e o `MeView` opera
sobre `request.user`. No instante em que existir `DELETE /api/auth/me/`, a
**segunda barreira deixa de cobrir a operação mais destrutiva do sistema** — a
camada de queryset vira a única defesa, que é exatamente a situação que
`tests/security/test_queryset_layer.py` foi escrito para impedir.

A omissão provavelmente é deliberada: uma policy `id = app.user_id` em `users`
quebraria o login, que consulta a tabela por e-mail **antes** de existir usuário
autenticado. Mas o login e o registro nunca entram no papel `remind_app` — o
contexto de RLS é aberto pelas classes de autenticação do DRF (`core/rls.py`),
e requisições pré-autenticação não passam por lá. Então a policy é viável; ela
só precisa ser escrita sabendo disso, e testada nos dois caminhos.

**2. `OutstandingToken.user` é `SET_NULL`, não `CASCADE`.** Medido:

```
tables      -> CASCADE      alert_rules -> CASCADE
records     -> CASCADE      alerts      -> CASCADE
token_blacklist_outstandingtoken -> SET_NULL
```

Os dados de domínio somem junto com a conta, corretamente. Os refresh tokens
**não**: ficam como linhas órfãs com `user_id = NULL`, criptograficamente
válidos até expirarem. Na prática o acesso já falha (a busca do usuário pelo
claim não acha ninguém), mas confiar nisso contraria o RS07, que fez o logout
colocar o token na blacklist justamente para "sair" significar alguma coisa.
Apagar a conta precisa invalidar explicitamente.

## Scope

### In-Scope

- Deploy no Railway: config 12-factor, gunicorn, WhiteNoise, topologia de serviços
- Imagem de produção do frontend com fallback SPA
- Cookie de refresh funcionando na topologia escolhida
- Throttling, health check sem vazamento, lockfile
- **Notificação por e-mail** (RF12 pelo canal `email`)
- **Busca textual** nos registros, API e UI
- **Recuperação de senha** por e-mail
- **Exclusão de conta** pelo próprio dono
- Backup/restore verificado e publicação pelo CI

### Out-of-Scope

- **Escolher o provedor de e-mail** — a Phase 0 decide. O Railway não oferece
  SMTP; é serviço externo (Resend, Postmark, SES, Mailgun…).
- Kubernetes, autoscaling, multi-região.
- Busca full-text com ranking, stemming ou fuzzy. O pedido é "barra de pesquisa
  que filtra colunas de texto" — substring com `ILIKE`, não um motor de busca.
- Digest diário por e-mail, preferências de frequência, unsubscribe granular.
- **Troca de e-mail da conta** com verificação do novo endereço. É um fluxo
  próprio, com sua própria armadilha (o endereço só muda depois de confirmado,
  senão um erro de digitação tranca a conta para fora).
- **Período de carência / restauração** de conta apagada. A exclusão da Phase 11
  é definitiva; "lixeira de 30 dias" é produto, não prontidão.
- Autenticação em dois fatores.
- Reescrever o que já passa nos testes.

---

## Phases

### Phase 0 — Duas decisões que mudam o trabalho ✅ concluída 2026-08-24

**Objective:** resolver as bifurcações antes de escrever código.

**Resultado:** `*.up.railway.app` (sem domínio próprio) + Resend para e-mail —
**e as duas eram incompatíveis**, o que só apareceu ao implantar a Phase 5. A
correção e a lição estão no **Status** no topo deste arquivo. A tabela de caminhos abaixo fica como registro do que foi
pesado — a linha "recomendado" **não** foi a escolhida, e isso é deliberado:
o custo de um domínio não se justificou nesta fase.

**Decisão 1 — domínios.** Recomendação: **domínio próprio, um só registrable
domain** (`app.exemplo.com` + `api.exemplo.com`). Mantém `SameSite=Lax`
funcionando, e `prod.py` já deriva `CSRF_TRUSTED_ORIGINS` de `ALLOWED_HOSTS`
exatamente para isso.

| Caminho | Custo |
|---|---|
| Domínio próprio, mesmo pai (**recomendado**) | comprar domínio; `Lax` continua valendo; CORS com origem exata |
| Só domínios `*.up.railway.app` | exige `SameSite=None; Secure` + validação no boot; mais superfície de CSRF |
| Um serviço só (nginx servindo SPA **e** fazendo proxy de `/api`) | sem CORS e sem cookie cross-site; um deploy acopla front e back |

**Decisão 2 — provedor de e-mail.** Critério: SMTP ou API, domínio verificado
(SPF/DKIM), e o que o remetente custa por mês no volume esperado. O código deve
falar SMTP por `EMAIL_BACKEND` para não amarrar o projeto a um fornecedor.

**Files Touched:** este arquivo (registrar as duas decisões no **Status**).

**Verify:** o cabeçalho **Status** nomeia a topologia e o provedor escolhidos.

---

### Phase 1 — Configuração que o Railway entende 🟢 concluída 2026-08-24

> Mesclada pelo PR #3. Verificado em CI, dentro do container: a imagem
> constrói, `collectstatic` roda no build com storage manifest e a suíte inteira
> passa, incluindo os testes de RLS com banco real. Em venv limpo:
> `test_cookie_policy.py` (10), `test_transport.py` (14, com `check --deploy
> --fail-level WARNING`), `ruff` limpo, dev inalterado.
>
> **O `docker/entrypoint.sh` ficou sem exercício até a Phase 2**, porque o
> compose sobrescreve `command:` em todo serviço e o CI nunca o executava. O job
> `producao` acrescentado na Phase 2 sobe o backend por ele — `migrate` seguido
> de `exec gunicorn` — e exige 200 no health. É o que fecha esta phase.


**Objective:** a aplicação lê o ambiente que a plataforma entrega, e é servida
por gunicorn.

- `DATABASE_URL` como fonte primária, com os `POSTGRES_*` atuais como fallback —
  o compose de desenvolvimento não pode regredir. `dj-database-url` resolve, ou
  um parse curto em `base.py`.
  **Preservar `ATOMIC_REQUESTS=True` e `CONN_MAX_AGE`**: a RLS depende do
  primeiro (`SET LOCAL` exige transação), e sobrescrever `DATABASES["default"]`
  inteiro é a forma óbvia de perdê-lo sem teste que reclame.
- `PORT` do ambiente no bind do gunicorn; `DJANGO_ALLOWED_HOSTS` aceitando
  `RAILWAY_PUBLIC_DOMAIN`.
- **WhiteNoise** logo após o `SecurityMiddleware`; `collectstatic` no build da
  imagem, não no start.
- Entrypoint roda `migrate` antes de servir.

**Cresceu pela Decisão 1 (`*.up.railway.app`).** Os quatro itens abaixo não
estavam no plano original; entraram porque dois registrable domains distintos
tiram o `Lax` da mesa:

- `AUTH_COOKIE_SAMESITE = "None"` em produção, **sempre** com
  `AUTH_COOKIE_SECURE = True`. `None` sem `Secure` é combinação que o browser
  descarta **em silêncio** — a sessão morreria a cada 15 min sem erro visível.
  `prod.py` levanta `ImproperlyConfigured` nessa combinação, mesmo padrão que
  ele já usa para `ALLOWED_HOSTS` vazio. Dev continua em `Lax`.
- **CORS por origem exata.** `CORS_ALLOWED_ORIGINS` com a URL do frontend
  literal e `CORS_ALLOW_CREDENTIALS = True`. Wildcard é inválido com
  credenciais — o browser rejeita `Access-Control-Allow-Origin: *` em
  requisição com cookie, então um `*` aqui falha em runtime, não no boot.
- **CSRF explícito.** `CSRF_TRUSTED_ORIGINS` precisa listar o domínio do
  frontend com esquema. Medido: `config/settings/prod.py:61` **já aceita** a
  variável de ambiente e só cai na derivação a partir de `ALLOWED_HOSTS` quando
  ela está vazia. Aquela derivação cobria o caso "mesmo pai"; com domínios
  distintos ela não basta, então isto é preencher a variável no Railway — não
  há código novo. Idem CORS: `corsheaders` já está em `INSTALLED_APPS` e no
  middleware (`base.py:36,53`), então a Decisão 1 custa configuração, não
  dependência.
- **Teste do trio.** `tests/security/test_cookie_policy.py` afirma, sob
  `prod.py`: `SameSite=None` implica `Secure`; a combinação `None` + não-`Secure`
  levanta `ImproperlyConfigured`; e a origem do frontend está em
  `CSRF_TRUSTED_ORIGINS`. Sem esse teste a regressão é silenciosa por
  construção.

**Files Touched:**
`config/settings/base.py` · `config/settings/prod.py` · `Dockerfile` ·
`docker/entrypoint.sh` (novo) · `requirements/base.txt` ·
`tests/security/test_transport.py` · `tests/security/test_cookie_policy.py` (novo)

**Verify:**
```bash
docker compose exec -T web pytest tests/security/ core/tests/test_rls.py -q
docker compose exec -T web env \
  DATABASE_URL=postgres://remind:remind@db:5432/remind \
  python -c "from django.conf import settings; import django; django.setup(); \
    d=settings.DATABASES['default']; assert d['ATOMIC_REQUESTS'], 'RLS quebrada'; print('DATABASE_URL ok')"
docker compose build web && docker compose up -d --wait web
docker compose exec -T web python manage.py collectstatic --noinput
```

---

### Phase 2 — Imagem de produção do frontend 🟢 concluída 2026-08-24

> Multi-estágio em `frontend/Dockerfile` (`dev` preservado, `producao` novo),
> `frontend/nginx.conf.template` com fallback de SPA, e `target: dev` fixado no
> compose. `VITE_API_URL` virou `ARG` com guarda: build sem a variável falha.
>
> **O job `producao` do CI fechou também o buraco da Phase 1.** Ele constrói as
> duas imagens de verdade, sobe o backend pelo `docker/entrypoint.sh`
> (`migrate` + `exec gunicorn`), exige 200 no health, verifica que o default de
> settings é produção — e no frontend testa fallback de SPA, 404 de asset
> ausente e a guarda do `ARG`. Até aqui, o caminho que vai para o Railway era o
> único do repositório que ninguém nunca executava.


**Objective:** servir o `dist/`, não o servidor do Vite.

- `frontend/Dockerfile` ganha estágios: o atual (dev, preservado) e `producao`,
  que roda `npm run build` e copia para uma imagem de nginx.
- **Fallback SPA obrigatório**: `try_files $uri $uri/ /index.html`. Sem isso as 8
  rotas do `App.tsx` dão 404 ao recarregar.
- `VITE_API_URL` como `ARG` de build — o Vite resolve `import.meta.env` na
  compilação. Consequência a documentar: **a imagem do frontend é específica do
  ambiente**; promover "a mesma imagem" de staging para produção apontaria para
  a API errada.
- Se a Phase 0 escolher "um serviço só", este nginx também faz proxy de `/api`.

**Files Touched:**
`frontend/Dockerfile` · `frontend/nginx.conf` (novo) · `docker-compose.yml`

**Verify:**
```bash
docker build -f frontend/Dockerfile --target producao \
  --build-arg VITE_API_URL=https://api.exemplo.com/api -t rt-front:prod .
docker run -d --rm -p 8080:80 --name rt-front rt-front:prod
curl -fsS http://localhost:8080/ | grep -q '<div id="root">'
curl -fsS -o /dev/null -w '%{http_code}\n' http://localhost:8080/tabelas/abc   # 200, não 404
docker rm -f rt-front
```

---

### Phase 3 — Serviços no Railway 🟢 concluída 2026-08-24 — no ar

> **Os seis serviços estão provisionados e respondendo:** Postgres, Redis,
> `web`, `worker`, `cron-alertas` (`*/15 * * * *`) e `frontend`. A API devolve
> `{"status":"ok","database":"up"}` e a SPA é servida.
>
> **O `preflight_db` passou nos cinco checks**, incluindo o `CREATE ROLE` — que
> era o risco em aberto capaz de forçar um redesenho do isolamento entre
> usuários. O RLS funciona no Postgres da plataforma.
>
> **A implantação custou quatro correções, e três delas não eram a causa.** O
> relato completo está em `docs`/artefato de estudo; o resumo:
>
> | Correção | Defeito real? | Era a causa do 502? |
> |---|---|---|
> | Host do healthcheck em `ALLOWED_HOSTS` (#11, #13) | sim | não |
> | `/api/health/` isento do SSL redirect (#11) | sim | não |
> | Escutar em IPv6 (#12) | sim | não |
> | **`PORT` fixado** (#14) | sim | **sim** |
>
> A causa: o Railway deriva a porta de destino do domínio do `EXPOSE` do
> Dockerfile, mas injeta `PORT=8080` no container. O processo obedecia a
> variável; a borda discava o `EXPOSE`. A conexão morria antes de virar
> requisição — por isso o log da aplicação ficava limpo com o domínio em 502.
>
> **A lição de método:** as três primeiras hipóteses nasceram de uma correlação
> lida em `.railway/railway.ts` — um arquivo que **nunca foi aplicado**. Não era
> observação, era inferência apresentada como fato. O que resolveu foi
> `railway logs --network`, uma fonte de dados fora da aplicação.
>
> ⚠️ **Falta um ajuste de painel:** o Start Command do `cron-alertas` ainda roda
> só a varredura — ver a nota da Phase 5.
>
> **Duas coisas que este plano dizia e estavam erradas:**
>
> 1. **`railway.toml` está descontinuado.** O Railway para de lê-lo em
>    2026-12-01 — três meses a partir de hoje. O substituto é Infrastructure as
>    Code (`.railway/railway.ts`). Foi a instrução deste próprio plano de
>    "confirmar contra a documentação vigente" que evitou o arquivo natimorto.
> 2. **`citext` e `pgcrypto` não são risco, porque não são usadas.** O e-mail
>    case-insensitive virou collation **ICU** quando o Django 5.1 removeu
>    `CIEmailField` (`accounts/models.py:18`), e os UUIDs vêm de `uuid.uuid4`
>    (`core/models.py:15`). O `init.sql` as cria por inércia. O risco real de
>    collation é o ICU, que é outra pergunta — e o `preflight_db` faz essa.
>
> **O risco do `CREATE ROLE` continua de pé e não foi resolvido — foi tornado
> mensurável.** `preflight_db` responde contra o banco real, sem deixar nada
> para trás, e sai com código != 0 para servir de gate antes do `migrate`.
>
> Nem tudo coube no IaC: `cronSchedule` e `restartPolicyType` não estão
> documentados para ele, só para o formato deprecado, então ficaram como ajuste
> de painel em vez de config não confirmada que falha na aplicação.


**Objective:** o projeto no ar.

Quatro serviços a partir do mesmo repositório, mais dois gerenciados:
`web` (gunicorn) · `worker` (celery) · `beat` · `frontend` (nginx) ·
Postgres e Redis gerenciados pela plataforma.

- `railway.toml` por serviço, com healthcheck apontando para `/api/health/`.
- **`beat` merece questionamento.** É um processo ocioso 24/7 para disparar uma
  task a cada 15 minutos. O cron da plataforma chamando um management command
  faz o mesmo por menos. A idempotência já é garantida pela constraint
  `alerts_idempotency`, então execução sobreposta não corrompe nada — a escolha
  é de custo, não de correção.
- Extensões: `docker/postgres/init.sql` cria `citext` e `pgcrypto`. No Postgres
  gerenciado não há hook de init — as extensões entram por migration ou por
  `psql` manual na primeira subida. **Verificar antes do primeiro `migrate`**,
  senão ele falha no meio.
- A RLS cria um papel `remind_app` `NOLOGIN`. Confirmar que o usuário do
  Postgres gerenciado tem permissão para `CREATE ROLE`.

> Confirmar contra a documentação vigente do Railway os nomes de variáveis
> (`RAILWAY_PUBLIC_DOMAIN`, `PORT`) e o formato do `railway.toml` — a plataforma
> muda, e este plano não é fonte para isso.

**Files Touched:**
`railway.toml` (novo) · `railway.json` (novo, se por serviço) ·
`.env.prod.example` (novo) · `README.md`

**Verify:**
```bash
railway up --service web
railway run --service web python manage.py check --deploy --fail-level WARNING
curl -fsS https://<dominio>/api/health/ | grep -q '"status": "ok"'
curl -fsS -o /dev/null -w '%{http_code}\n' https://<dominio-front>/tabelas/abc   # 200
# O cookie de refresh sobrevive à troca de página — a armadilha da Phase 0:
#   logar na SPA, esperar o access expirar (15 min), navegar. Continuar logado.
```

---

### Phase 4 — Endurecimento da superfície pública 🟢 concluída 2026-08-24

> Throttling com taxas do ambiente e teto separado no export; health que não
> vaza mais host/porta/usuário; Admin e `/api/docs/` desligados por default em
> produção.
>
> **Duas coisas que o plano não previa e apareceram ao implementar:**
>
> 1. **`NUM_PROXIES` era obrigatório, não detalhe.** Sem ele o `get_ident` do
>    DRF usa o `X-Forwarded-For` inteiro como identidade, e quem manda um valor
>    diferente a cada requisição nunca alcança o teto. Medido: `1.2.3.4,
>    203.0.113.7` e `9.9.9.9, 203.0.113.7` viravam clientes distintos.
> 2. **O cache precisou sair do LocMem**, senão cada worker do gunicorn teria o
>    seu contador — e, junto, precisou de um limitador que **falha aberto**
>    (`core/throttling.py`), para uma queda do Redis não virar 500 em toda
>    requisição. Sem isso a phase ampliaria a indisponibilidade que ela existe
>    para reduzir.
>
> **Correção posterior (2026-08-25, achada rodando a suíte da Phase 7).**
> `test_anonimo_leva_429_ao_passar_do_limite` era **flaky**: o contador anônimo
> é por IP, e o healthcheck do `docker-compose` bate em `/api/health/` a cada
> 10s a partir do mesmo `127.0.0.1`, no processo do runserver, incrementando a
> mesma chave no mesmo Redis. Quando o healthcheck caía dentro da janela do
> teste, a terceira requisição já voltava 429. Medido: falha reproduzível com o
> healthcheck ligado, 7/7 verdes com ele desligado. A correção é o teste passar
> um `REMOTE_ADDR` só dele — 3/3 verdes com o healthcheck de volta. O CI corria
> o mesmo risco: `up -d --wait web` deixa o healthcheck ativo durante o
> `pytest --cov`.


**Objective:** fechar o que só aparece sob tráfego real.

- **Throttling** com escopo próprio, mais apertado no export. Taxas do ambiente.
- **Health check para de vazar**: o 503 devolve `{"status": "unhealthy",
  "database": "down"}` e o `str(exc)` vai para o log, onde o `RedactingFilter` já
  atua. Teste provando que a resposta não contém host, porta nem usuário.
- **Admin e `/api/docs/`** atrás de variável de ambiente. O schema é a planta da
  API; publicá-lo é escolha, não default.

**Files Touched:**
`config/settings/base.py` · `config/settings/prod.py` · `core/views.py` ·
`config/urls.py` · `exports/views.py` ·
`tests/security/test_health_leak.py` (novo) · `tests/security/test_throttling.py` (novo)

**Verify:**
```bash
docker compose exec -T web pytest tests/security/ -q
```

---

### Phase 5 — Notificação por e-mail 🟢 concluída 2026-08-24

> **Duas coisas que o plano não previa, resolvidas na implementação:**
>
> 1. **Retry precisou de estado no banco.** "Retry com limite e backoff" não
>    cabia sem contador: o cron roda a cada 15 minutos e não sabe o que a
>    execução anterior fez. Sem `delivery_attempts`, um endereço inexistente
>    seria retentado para sempre; sem `last_attempt_at`, não há backoff.
>    Migration `alerts.0002`. `updated_at` foi considerado e descartado —
>    qualquer outra escrita no alerta o move.
> 2. **O default de `EMAIL_BACKEND` é console em dev e SMTP em produção.**
>    Herdar o console em produção seria a pior falha possível: o envio
>    "funcionaria", os alertas virariam `SENT`, o log encheria de e-mails
>    bonitos e ninguém receberia nada. Falha que se parece com sucesso.
>
> **Cron:** os dois comandos rodam no mesmo serviço, com invólucro de shell:
>
> ```
> sh -c "python manage.py scan_alerts; python manage.py send_alert_emails"
> ```
>
> `;` e não `&&` — com `&&`, uma varredura que falhasse pularia a entrega dos
> pendentes que já estavam na fila.
>
> `sh -c` porque o Railway executa o start command em **exec form** para serviço
> vindo de Dockerfile: não há shell, e `;` viraria mais um argumento do
> `manage.py`. Isto foi documentado errado primeiro — o custo de descobrir na
> plataforma o que a plataforma documenta.
>
> **Provedor: SMTP do Gmail**, não o Resend que a Phase 0 escolheu — as duas
> decisões da Phase 0 eram incompatíveis, e isso só apareceu aqui. Ver a nota
> no **Status**, no topo. Nenhuma linha de código mudou por causa disso.
>
> **Configurado e verificado em 2026-08-24:** `EMAIL_HOST`, `EMAIL_PORT`,
> `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` (senha de app) e
> `DEFAULT_FROM_EMAIL` em `worker` e `cron-alertas`. O transporte foi provado
> com um envio real, e não pela suíte: os testes usam `locmem`, que aceita
> qualquer endereço — **nada neles revela um provedor mal configurado**.
>
> ⚠️ **Falta fora do código:** o Start Command do `cron-alertas` precisa rodar
> os dois comandos (`scan_alerts; send_alert_emails`); hoje roda só a varredura.

**Objective:** fechar a costura que `alerts/services.py` já deixou aberta.

O trabalho é **completar**, não criar: o canal, os status `PENDING`/`FAILED` e a
lógica de `delivered_immediately` já existem.

- `EMAIL_BACKEND` SMTP configurado por ambiente; em teste, o backend `locmem`.
- Task `alerts.send_pending_emails`: pega `status=PENDING, channel=email`,
  envia, e marca `SENT` (com `notified_at`) ou `FAILED`. Separada da varredura,
  porque gerar e entregar falham por motivos diferentes e não devem cair juntas.
- **Retry com limite e backoff.** Provedor fora do ar não pode virar fila infinita
  nem e-mail duplicado: a transição de status é a trava, e ela precisa ser feita
  com `select_for_update` ou update condicional (`filter(status=PENDING).update(...)`),
  não lida-e-depois-grava.
- **RS05 vale para o corpo do e-mail.** O template usa o mesmo `record_label()`
  que o alerta in-app — que já pula colunas `is_sensitive`. O e-mail **não pode**
  carregar o `data` do registro: ele sai do perímetro do sistema e fica na caixa
  de entrada de alguém para sempre. Teste provando que valor de coluna sensível
  não aparece no corpo.
- Regra de e-mail configurável na UI: a tela de regras (`TabelaRegras.tsx`) já
  existe e mostra antecedência; falta expor o seletor de canal.
- Falha de envio não pode derrubar a varredura.

**Files Touched:**
`config/settings/base.py` · `alerts/tasks.py` · `alerts/services.py` ·
`alerts/templates/alerts/vencimento.txt` (novo) ·
`alerts/templates/alerts/vencimento.html` (novo) ·
`alerts/tests/test_email_delivery.py` (novo) ·
`tests/security/test_email_redaction.py` (novo) ·
`frontend/src/routes/TabelaRegras.tsx` · `frontend/src/api/alerts.ts`

**Verify:**
```bash
docker compose exec -T web pytest alerts/ tests/security/test_email_redaction.py -q
# Sem provedor: console backend mostra o e-mail montado, com o rótulo seguro.
docker compose exec -T web env EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend \
  python manage.py shell -c "from alerts.tasks import send_pending_emails; send_pending_emails()"
cd frontend && npm run test -- src/routes/TabelaRegras
```

---

### Phase 6 — Busca nas colunas de texto 🟢 concluída 2026-08-24

> `?q=` no `RecordFilter`, `BarraBusca` com debounce de 350 ms e estado na URL.
> Colunas `is_sensitive` e `select` ficam de fora — com teste para cada uma.
>
> **Medido antes de escrever:** o SQL de `data__<key>__icontains` e o de
> `KeyTextTransform` são idênticos — o Django já usa `->>`, não `->`. A busca
> não enxerga as aspas do JSON, então a forma simples do plano estava certa e
> não precisou de anotação.
>
> **Índice: nada feito, como previsto.** `records_data_gin` usa
> `jsonb_path_ops` e não acelera `ILIKE`; a varredura sequencial foi aceita
> nesta fase. `pg_trgm` entra quando doer — e o gatilho de replanejamento
> abaixo continua valendo.


**Objective:** `?q=` na API e barra de pesquisa na tela.

- `?q=` no `RecordFilter`, casando **apenas nas colunas de tipo texto da
  tabela**: para cada coluna, `data__<key>__icontains`, tudo em `OR`. A tabela
  já está delimitada, então a lista de colunas é conhecida e curta — o mesmo
  padrão que `RecordFilterBackend` já usa para injetar contexto no FilterSet.
- **Colunas `is_sensitive` ficam de fora da busca.** A UI mascara esses valores
  (`CelulaValor.tsx`); deixá-los pesquisáveis permitiria confirmar um valor por
  tentativa — o mascaramento viraria enfeite. Decisão a registrar em comentário,
  com teste.
- Quais tipos entram: `text` e `email` são texto de verdade. `select` é
  domínio fechado e já tem filtro próprio — fora. Decisão explícita, não
  implícita.
- **O índice atual não ajuda.** `records_data_gin` usa `jsonb_path_ops`, que
  serve a `@>` e não a `ILIKE`. Aceitar varredura sequencial nesta fase e medir;
  se doer, o caminho é `pg_trgm` com índice de expressão por coluna.
- UI: campo de busca com *debounce*, estado **na URL** como os outros filtros
  (`useTabelaServidor`), e reset de página ao buscar — o mesmo comportamento que
  `FiltroStatus` já tem. Com resultado vazio, dizer que a busca não achou nada,
  distinguindo de "a tabela está vazia".

**Files Touched:**
`records/filters.py` · `records/views.py` ·
`records/tests/test_search.py` (novo) ·
`frontend/src/components/BarraBusca.tsx` (novo) ·
`frontend/src/hooks/useTabelaServidor.ts` · `frontend/src/routes/TabelaRegistros.tsx` ·
`frontend/src/api/records.ts` · `frontend/src/components/BarraBusca.test.tsx` (novo)

**Verify:**
```bash
docker compose exec -T web pytest records/tests/test_search.py -q
cd frontend && npm run test -- src/components/BarraBusca src/routes/TabelaRegistros
cd frontend && npm run typecheck && npm run lint
```

---

### Phase 7 — Builds reproduzíveis 🟢 concluída 2026-08-25

**Objective:** a mesma imagem, construída em datas diferentes, instala as mesmas
versões.

`pip-compile` gerando `requirements/*.lock` com hashes; `Dockerfile` instala do
`.lock` com `--require-hashes`; passo de CI que falha se o lock estiver
dessincronizado — mesmo princípio do job `contrato`, que já guarda a fronteira
schema↔cliente.

**Files Touched:**
`requirements/base.lock` (novo) · `requirements/dev.lock` (novo) ·
`requirements/base.txt` · `requirements/dev.txt` · `Dockerfile` · `Makefile` ·
`.github/workflows/ci.yml` · `README.md`

**O check compara PINS, não hashes — e isso foi medido, não presumido.** A
primeira versão recompilava com `--generate-hashes` e comparava o arquivo
inteiro. Custo real: `--generate-hashes` **baixa todo artefato resolvido** para
calcular o hash — **~4 minutos**, e nesta máquina o passo terminou em
`ReadTimeoutError` de `files.pythonhosted.org` **duas vezes seguidas**, com os
locks perfeitamente em dia. Um check que reprova PR correto por timeout de
download é pior que não ter check: ensina a ignorar o vermelho.

Sem hashes, a mesma recompilação leva **~11 s** e responde a pergunta que
importa — "o lock reflete o `.txt`?" —, porque isso está nos pins
(`nome==versão`, transitivas incluídas). A integridade dos artefatos continua
cobrada onde tem efeito: o `pip install --require-hashes` do `Dockerfile` recusa
qualquer artefato que não case com o hash declarado, no build.

A receita mora no `Makefile` (`make locks` / `make locks-check`); o CI **chama o
alvo** em vez de repetir o comando no workflow. Duas cópias do mesmo script
divergem em silêncio, e a que decide o merge seria justamente a que ninguém roda
na máquina.

**Verify:**
```bash
make locks-check                       # ~11 s; "locks em dia"
docker compose build web               # dev.lock, --require-hashes
docker build --build-arg REQUIREMENTS=base.lock -t rt-api:prod .
docker compose exec -T web pytest -q
```

Testado também o caminho negativo: `requests>=2.32` acrescentado ao `base.txt`
sem regenerar o lock → `locks-check` sai com 1 e imprime o diff, com
`requests==2.34.2` e `urllib3==2.7.0` (a transitiva) faltando no lock.

**Não coberto, de olho aberto:** a tag `python:3.12-slim` e os pacotes `apt` do
`Dockerfile` continuam móveis. Pinar a imagem base por digest custaria nunca
receber correção de segurança sem alguém lembrar de bumpar.

---

### Phase 8 — Backup e restore 🟡 em andamento (2026-08-25)

**Objective:** provar o **restore**, não só agendar o dump. Backup não testado é
suposição.

O Railway faz snapshot do Postgres gerenciado, mas um backup que só existe
dentro do fornecedor não protege contra apagar a conta ou o serviço. Dump
próprio, com retenção, e um restore exercitado.

**Files Touched:**
`docker/backup.sh` (novo) · `docker/restore.sh` (novo) · `Makefile` ·
`README.md` · `.gitignore`

> **A suposição era falsa, e o ensaio pegou.** Restaurando o dump direto num
> cluster limpo:
>
> ```
> ERROR:  role "remind_app" does not exist
> ```
>
> `pg_dump` de um BANCO não carrega objetos de CLUSTER. O dump traz os
> `GRANT ... TO remind_app` (são do banco), mas não o `CREATE ROLE` nem o
> `GRANT remind_app TO <dono>` — e o restore aborta na seção de privilégios
> **depois** de já ter carregado tabelas e dados. Medido nesse estado:
> `records=5`, `users=3`, **`grants para remind_app = 0`**.
>
> O banco parece restaurado e a aplicação não lê uma linha: quem executa
> consulta de usuário é `remind_app` (RS01), e ele ficou sem privilégio nenhum.
> Sem `ON_ERROR_STOP=1`, o `psql` teria saído com status 0 — um restore
> "bem-sucedido" que só falha quando alguém tenta usar o sistema.
>
> `docker/restore.sh` cria o papel ANTES de carregar, com o mesmo DDL da
> migration `core/0001_rls_policies`. Depois disso: 20 tabelas, 5 policies,
> 80 grants, 3 users, 3 tables, 5 records, rc=0.

**Duas decisões de desenho que vieram disso:**

1. **`make restore-ensaio` é o alvo central**, não um extra. Sobe um Postgres
   descartável, restaura o backup mais recente, conta o que voltou e destrói o
   cluster — sem encostar no banco local. É o único jeito de o restore continuar
   provado depois de hoje. O ensaio sobe o cluster **sem** o `init.sql` das
   extensões de propósito: `citext` e `pgcrypto` têm que vir do dump.
2. **O dono do banco é lido do próprio arquivo** (`ALTER DEFAULT PRIVILEGES FOR
   ROLE ...`), não do `.env`. No cenário que o ensaio simula — o fornecedor
   sumiu — o dump é tudo o que restou.

**Verify:**
```bash
sh docker/backup.sh                                  # ✅ 15 kB, marcador final conferido
sh docker/restore.sh --ensaio                        # ✅ rc=0, contagens acima
sh docker/restore.sh backups/x.sql.gz                # ✅ recusa sem CONFIRMA=sim
CONFIRMA=sim DATABASE_URL=... sh docker/restore.sh   # ✅ recusa alvo remoto
CONFIRMA=sim make restore BACKUP=backups/x.sql.gz    # ⏳ pendente — ver abaixo
```

**Pendente:** o caminho destrutivo (`make restore`) ainda não foi exercitado
ponta a ponta — apaga o banco de desenvolvimento, e a execução foi barrada por
falta de permissão na sessão. O que ele tem de próprio em relação ao ensaio:
parar `web`/`worker`/`beat`, encerrar conexões abertas, `DROP`/`CREATE DATABASE`
e subir o `web` de volta. As guardas (sem `CONFIRMA`, com `DATABASE_URL`,
arquivo inexistente) já foram testadas e recusam corretamente.

---

### Phase 9 — Observabilidade e CD 🟢 concluída 2026-08-25

**Objective:** saber que quebrou antes do usuário contar.

**Files Touched:**
`core/views.py` · `core/urls.py` · `core/observabilidade.py` (novo) ·
`config/settings/prod.py` · `requirements/base.txt` + os dois `.lock` ·
`.github/workflows/ci.yml` · `.env.example` · `.env.prod.example` ·
`README.md` · `core/tests/test_health.py` ·
`tests/security/test_observability_redaction.py` (novo) ·
`tests/security/test_throttling.py` · `tests/security/test_auth_required.py`

> **O health estava sujeito ao limite de taxa, e ninguém tinha ligado os
> pontos.** Os endpoints são `AllowAny`, então caíam no teto `anon` — 60/hour.
> Um monitor batendo a cada 10s faz 360/hour: a partir do 61º a plataforma e o
> painel recebem **429**, e a leitura disso é "a aplicação caiu" com ela
> perfeitamente de pé. O sintoma já estava no log do compose desde a Phase 4 —
> `Too Many Requests: /api/health/`, vindo do healthcheck do próprio container —
> e foi lido como ruído até virar a falha flaky da Phase 8. Agora os dois
> endpoints de observação são isentos, com teste.
>
> Efeito colateral: `test_anonimo_leva_429_ao_passar_do_limite` usava o health
> como sonda e virou tautologia. A sonda passou a ser `GET /api/auth/login/`
> (405) — o DRF checa throttle em `initial()`, antes de resolver o handler do
> método, então um método não permitido é a sonda anônima mais limpa que existe:
> não autentica, não escreve `AccessAttempt` do django-axes, não depende de
> fixture.

**1. Liveness e readiness separados por CONSEQUÊNCIA, não por rigor**

`/api/health/` (banco) continua sendo o que a plataforma consulta; o novo
`/api/health/ready/` cobre banco **e Redis**. O Redis fica fora da liveness de
propósito: um health que a plataforma consulta é gatilho de *restart*, e com o
Redis na conta uma queda do cache — que hoje só degrada throttle e alertas,
porque `core/throttling.py` falha aberto — passaria a reiniciar todos os
containers de `web` em laço, sem que reiniciar consertasse nada. Seria
transformar degradação em indisponibilidade, que é o que a Phase 4 recusou.

Medido com o Redis parado: `ready` 503 `{"database":"up","redis":"down"}`,
liveness 200.

**2. A configuração do rastreador é um VALOR, não uma chamada**

`sentry_sdk.init(...)` solto em `prod.py` não deixa ninguém afirmar nada: não se
testa uma chamada. As opções viraram um dicionário em `core/observabilidade.py`,
e cada invariante está sob teste — `send_default_pii=False`,
`max_request_body_size="never"`, `before_send` e `before_send_transaction`
apontando para o mesmo `scrub` do `RedactingFilter`. Um `send_default_pii=True`
acrescentado por conveniência (é o que todo tutorial sugere) fica vermelho antes
de virar vazamento.

E a redação vai no `before_send`, não na confiança no filtro de log: o
`RedactingFilter` está pendurado nos *handlers*, e a integração de logging do SDK
não é um handler nosso — ela se enxerta no caminho do `logging` e vê o
`LogRecord` por conta própria. Depender disso seria depender de ordem entre
bibliotecas, que não é contrato.

**3. "CI publica no push para main" foi reinterpretado — e o motivo está medido
no repositório**

O plano é de 2026-08-21 e a linha assumia que o CI implantaria. Não é o caso:
`.railway/railway.ts` declara `source: github(REPO, { branch: BRANCH })`, então o
push para `main` **já dispara o deploy**. Escrever um `railway up` no workflow
criaria um segundo caminho de implantação — dois jeitos de colocar código no ar,
um deles usado só às vezes, é como se ganha uma diferença entre o que se testou
e o que está rodando.

O que faltava de verdade era o **interlock**: o Railway observa o branch, não os
checks, e implanta um push com o CI vermelho. Isso é ajuste de painel (**Wait for
CI**), registrado no README junto dos outros que a Phase 3 já listava.

O job novo (`pos-deploy`, só em push para `main`) faz o que o CI pode fazer de
útil depois do deploy: espera `/api/health/ready/` na URL de produção reportar
`status: ok` — o que inclui o Redis, que o healthcheck da plataforma não olha.
Gated pela variável de repositório `URL_PRODUCAO`; sem ela, avisa e passa.
Limitação registrada em comentário e no README: **não prova que a revisão nova é
a que responde** — sem endpoint de versão, um 200 pode vir da revisão anterior.

**Os tripwires funcionaram.** A rota nova quebrou dois testes de guarda —
`test_every_api_route_is_classified` (rota não classificada como pública ou
protegida) e `test_the_whole_api_surface_is_documented` (21 caminhos no schema
para 20 classificados). Nenhum dos dois é sobre health: são sobre não deixar
endpoint entrar sem decisão de permissão e sem documentação.

**Verify:**
```bash
docker compose exec -T web pytest tests/security/ core/tests/ -q   # ✅ 66 nos arquivos tocados
curl -s localhost:8000/api/health/ready/     # ✅ {"status":"ok","database":"up","redis":"up"}
docker compose stop redis
curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/api/health/ready/   # ✅ 503
curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/api/health/         # ✅ 200 (liveness intacta)
docker compose start redis
```

Também exercitado: 160 requisições seguidas nos dois endpoints, todas 200 — sem
a isenção, a 61ª seria 429.

---

### Phase 10 — Recuperação de senha por e-mail

**Depende da Phase 5** (backend de e-mail configurado).

**Objective:** quem esqueceu a senha volta a entrar, sem que o fluxo vire um
oráculo de quais e-mails têm conta.

- Dois endpoints: pedir o link e consumir o token.
- **Token do `PasswordResetTokenGenerator` do Django**, não um token próprio. Ele
  deriva o hash da senha atual e do `last_login`, então **usar uma vez o
  invalida** — sem tabela nova, sem coluna nova, sem rotina de expurgo. Escrever
  um token próprio aqui seria refazer, pior, o que a stdlib do framework já faz.
- **A resposta é idêntica exista ou não a conta.** Sempre 204, sempre a mesma
  mensagem na tela. Um 404 para e-mail desconhecido transformaria o endpoint em
  verificador de cadastro — o mesmo raciocínio do RS04, que devolve 404 em vez
  de 403 para não confirmar que um recurso existe. Teste comparando as duas
  respostas byte a byte.
- **O link aponta para o frontend**, não para a API: `FRONTEND_URL` entra como
  variável de ambiente (`/redefinir-senha?uid=…&token=…`), porque quem renderiza
  o formulário é a SPA.
- **Redefinir invalida todas as sessões**: blacklist dos refresh tokens em
  aberto. Sem isso, quem roubou um refresh continua dentro por 7 dias
  **justamente depois** de a vítima trocar a senha por suspeitar do roubo.
  É o RS07 aplicado ao caso em que ele mais importa.
- **Limpar o bloqueio do django-axes** ao redefinir com sucesso: quem esqueceu a
  senha erra várias vezes antes de pedir o link, e chegaria ao fim do fluxo
  ainda travado, sem entender por quê.
- Throttling apertado nos dois endpoints (Phase 4): é vetor de spam para caixas
  de terceiros.
- A senha nova passa pelos mesmos validadores do registro.

**Files Touched:**
`accounts/views.py` · `accounts/serializers.py` · `accounts/urls.py` ·
`config/settings/base.py` ·
`accounts/templates/accounts/redefinir_senha.txt` (novo) ·
`accounts/tests/test_password_reset.py` (novo) ·
`tests/security/test_user_enumeration.py` (novo) ·
`frontend/src/routes/EsqueciSenha.tsx` (novo) ·
`frontend/src/routes/RedefinirSenha.tsx` (novo) ·
`frontend/src/routes/Login.tsx` · `frontend/src/App.tsx` · `frontend/src/api/auth.ts`

**Verify:**
```bash
docker compose exec -T web pytest accounts/tests/test_password_reset.py \
  tests/security/test_user_enumeration.py -v
# O token é de uso único e a sessão antiga morre:
docker compose exec -T web pytest -k "reset_token_cannot_be_reused or reset_blacklists" -v
cd frontend && npm run test -- src/routes/EsqueciSenha src/routes/RedefinirSenha
```

---

### Phase 11 — Exclusão de conta

**Depende da Phase 10** (compartilha o padrão de reautenticação) e da Phase 5
(e-mail de confirmação).

**Objective:** o dono apaga a própria conta, e o que sai do sistema sai de
verdade.

- `DELETE /api/auth/me/` — o `MeView` passa de `RetrieveUpdateAPIView` para
  `RetrieveUpdateDestroyAPIView`.
- **Exige a senha atual no corpo**, mesmo com o usuário autenticado. Um access
  token roubado não pode apagar a conta da vítima; e a operação é irreversível,
  o que é razão suficiente para pedir a prova outra vez.
- **Política de RLS na tabela `users`** (ver *Estado atual*), self-only, escrita
  sabendo que login e registro rodam **fora** do papel `remind_app` e portanto
  não são afetados. Sem ela, a exclusão é a única operação destrutiva do sistema
  sem a segunda barreira. Teste nos dois caminhos: autenticado (só a própria
  linha visível) e pré-autenticação (login continua funcionando).
- **Blacklist explícito dos refresh tokens** antes de apagar — `SET_NULL` deixa
  os tokens órfãos, e o RS07 diz que invalidação é do sistema, não do acaso.
- O cascade cuida do resto: `tables`, `records`, `alert_rules` e `alerts` são
  todos `CASCADE`. Teste contando linhas nas cinco tabelas antes e depois, com
  **um segundo usuário presente** — para provar que a exclusão de um não leva
  nada do outro junto.
- E-mail de confirmação **depois** do fato, informando o que foi apagado. Não é
  cerimônia: é como a vítima de uma conta comprometida descobre.
- UI: confirmação por digitação do e-mail, não um "tem certeza?". O
  `DialogoConfirmar` já existe e é reusado.

**Files Touched:**
`accounts/views.py` · `accounts/serializers.py` ·
`core/migrations/0003_users_rls_policy.py` (novo) ·
`accounts/templates/accounts/conta_excluida.txt` (novo) ·
`accounts/tests/test_account_deletion.py` (novo) ·
`core/tests/test_rls.py` · `tests/security/test_cross_tenant.py` ·
`frontend/src/routes/Conta.tsx` (novo) · `frontend/src/components/Layout.tsx` ·
`frontend/src/App.tsx` · `frontend/src/api/auth.ts`

**Verify:**
```bash
docker compose exec -T web pytest accounts/tests/test_account_deletion.py \
  core/tests/test_rls.py tests/security/ -q
# A policy nova não pode quebrar o login, que consulta `users` sem contexto:
docker compose exec -T web pytest accounts/tests/test_auth.py -q
# Apagar A não pode tocar em B:
docker compose exec -T web pytest -k "deletion_leaves_other_user_intact" -v
cd frontend && npm run test -- src/routes/Conta
```

---

## Ordem

**Bloqueadoras para existir em produção:** 0 → 1 → 2 → 3.
**Bloqueadora para exposição pública:** 4.
**Features pedidas:** 5 (e-mail) → 10 (recuperação de senha) → 11 (exclusão de
conta) formam uma corrente: as duas últimas mandam e-mail, e a 11 reusa o padrão
de reautenticação da 10. A Phase 6 (busca) é independente de todas e pode ser
feita a qualquer momento — é a única feature sem pré-requisito nenhum.

Nada dessa corrente depende do deploy, então ela roda em paralelo às phases de
infra, desde que a Phase 5 espere a decisão de provedor da Phase 0.

**Qualidade de operação:** 7, 8, 9 — independentes entre si.

```
0 ──► 1 ──► 2 ──► 3 ──► 4          (produção)
└───► 5 ──► 10 ──► 11              (e-mail e conta)
      6                            (busca — sem pré-requisito)
      7 · 8 · 9                    (operação)
```

## O que dispara replanejamento

- ~~**A Phase 0 escolher os domínios `*.up.railway.app`**~~ → **DISPARADO em
  2026-08-24.** `SameSite=None` virou obrigatório, e com ele CSRF explícito e
  CORS por origem exata. A Phase 1 já foi crescida para absorver isso; ver o
  bloco "Cresceu pela Decisão 1" nela.
- **O Postgres gerenciado não permitir `CREATE ROLE`** → a RLS não sobe como
  está. É a barreira do RS01, não um detalhe: sem ela o isolamento volta a ser só
  a camada de queryset. Descobrir isso **na Phase 3, antes de migrar dados** —
  a alternativa é papel criado pelo suporte da plataforma ou outro provedor de
  banco.
- ~~**`citext`/`pgcrypto` indisponíveis no Postgres gerenciado**~~ → **premissa
  falsa, verificada em 2026-08-24.** Nenhuma das duas é usada. O gatilho certo é
  **ICU indisponível**, que derruba `accounts.0001` (a collation
  `und-u-ks-level2` de `users.email`); a alternativa continua sendo normalizar na
  aplicação, mais fraca e com teste próprio. `preflight_db` checa isso.
- **A busca da Phase 6 ficar lenta** (varredura sequencial em tabela grande) →
  entra `pg_trgm` com índice de expressão. Medir antes: a maioria das tabelas
  não chega ao tamanho em que isso importa.
- **O provedor de e-mail exigir API própria em vez de SMTP** → a Phase 5 troca o
  backend por um cliente específico, e o teste com `locmem` deixa de cobrir o
  caminho real; passa a exigir um teste de contrato contra o sandbox do
  fornecedor.
- **Precisar de mais de uma réplica de `web`** → o `migrate` do entrypoint vira
  job separado, e o `beat` precisa de eleição de líder (ou vira cron da
  plataforma, como a Phase 3 já sugere).
- **A policy de RLS em `users` (Phase 11) quebrar algum caminho
  pré-autenticação** — login, registro, `createsuperuser`, o Admin — → recuar
  para policy só de `DELETE`/`UPDATE`, deixando `SELECT` livre. A tabela seria
  legível pelo papel, o que já é o caso hoje, mas a operação destrutiva ficaria
  coberta. Recuar de vez, sem policy nenhuma, é decisão consciente que precisa
  ficar escrita — não silêncio.
- **Descobrir que a exclusão precisa ser reversível** (exigência legal,
  arrependimento de usuário) → vira `is_active=False` + expurgo agendado, e a
  Phase 11 muda de forma: o cascade deixa de ser o mecanismo, e passa a existir
  estado "conta apagada mas com dados" que todo queryset precisa respeitar.
  Decidir **antes** de implementar; converter depois é migração de dados.
