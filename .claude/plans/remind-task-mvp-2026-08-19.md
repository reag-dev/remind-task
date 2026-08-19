# Plan: remind-task — Sistema de Alertas e Tabelas Dinâmicas (MVP backend)

**Date:** 2026-08-19
**Status:** active — Phases 0-6 concluídas em 2026-08-19; Phases 7-9 pendentes
**Stack:** Django 5 + DRF + PostgreSQL 16 + Celery/Redis + Docker Compose

## Goal

Entregar o backend MVP do sistema de tabelas dinâmicas com controle de vencimentos, alertas assíncronos idempotentes e isolamento de dados por usuário em duas camadas (queryset + RLS no Postgres).

## Scope

### In-Scope
- Modelagem definitiva do banco (seção **Modelo de dados** abaixo) + migrations Django.
- Apps: `accounts`, `tables`, `records`, `alerts`, `exports`, `core`.
- API REST (DRF) cobrindo RF01–RF13.
- Job Celery Beat de geração de alertas com idempotência garantida por constraint no banco.
- Row-Level Security no Postgres com dois roles (migrator/runtime).
- Suite de testes de segurança cobrindo os 10 critérios da seção 10 da especificação.
- Docker Compose de desenvolvimento (web + db + redis + worker + beat).

### Out-of-Scope
- **Frontend SPA.** A "UI" do MVP é a *DRF Browsable API* + Django Admin + OpenAPI (`drf-spectacular`). React/Next fica para um plano posterior.
- Notificação por e-mail (RF12 evolução) — o modelo já prevê `channel`, mas só `in_app` é implementado.
- Criptografia em repouso de campos sensíveis (`pgcrypto`) — apenas a flag `is_sensitive` e a redação em logs.
- Compartilhamento de tabelas, permissões multi-usuário, histórico/auditoria, importação CSV, recorrência.
- Deploy em produção (Render/Fly). O plano para em "roda em Docker Compose local com testes verdes".

---

## Modelo de dados

### Decisão central: JSONB híbrido, não EAV puro

A especificação sugere `RecordValue(record_id, column_id, value)` — EAV clássico. **Rejeitado.** Motivos:

| Problema do EAV | Impacto direto nos requisitos |
|---|---|
| N linhas por registro; listar 50 registros de 6 colunas = 300 linhas + pivot | RF04, RF11 viram consulta cara e complexa |
| `value` é `TEXT` → ordenar por data exige cast por linha, sem índice útil | RF11 (ordenação por vencimento) fica O(n) sem índice |
| Varrer vencimentos exige join + filtro em `value` textual | RF12 (job periódico) fica lento e frágil |
| Export precisa pivotar em SQL ou em Python | RF13 vira N+1 |

**Adotado:** `records.data JSONB` (1 linha por registro) **+ colunas promovidas** para o que o sistema precisa consultar (`due_date`). Combina a flexibilidade do EAV com performance de coluna nativa nos dois pontos quentes: ordenação e varredura de alertas.

Chave do JSONB = `columns.key` (slug **imutável** gerado na criação da coluna), não `columns.id` e não `columns.name`. Assim renomear a coluna (RF05) não reescreve nenhum registro, e o payload continua legível.

### DDL conceitual

> **Este bloco é o desenho original, preservado como registro.** O schema vigente
> mora em [`docs/data-model.md`](../../docs/data-model.md) e já diverge daqui em
> dois pontos, ambos justificados lá: `users.email` usa collation
> não-determinística em vez de `CITEXT` (as classes `CIText*` saíram do Django em
> 5.1) e `columns.type` é varchar + CHECK em vez de ENUM nativo.

```sql
-- =========================================================
-- accounts
-- =========================================================
CREATE TABLE users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         CITEXT       NOT NULL UNIQUE,      -- USERNAME_FIELD
    name          VARCHAR(120) NOT NULL,
    password      VARCHAR(128) NOT NULL,             -- argon2id (Django)
    timezone      VARCHAR(64)  NOT NULL DEFAULT 'America/Sao_Paulo',
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    is_staff      BOOLEAN      NOT NULL DEFAULT FALSE,
    last_login    TIMESTAMPTZ,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- =========================================================
-- tables
-- =========================================================
CREATE TABLE tables (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name             VARCHAR(120) NOT NULL,
    description      TEXT NOT NULL DEFAULT '',
    alert_lead_days  SMALLINT NOT NULL DEFAULT 3
                       CHECK (alert_lead_days BETWEEN 0 AND 365),  -- limiar "próximo do vencimento" (RF10)
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT tables_unique_name_per_user UNIQUE (user_id, name)
);
CREATE INDEX tables_user_created_idx ON tables (user_id, created_at DESC);

-- =========================================================
-- columns
-- =========================================================
CREATE TYPE column_type AS ENUM (
    'text','number','date','datetime','boolean','email','select','due_date'
);

CREATE TABLE columns (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    table_id     UUID NOT NULL REFERENCES tables(id) ON DELETE CASCADE,
    key          VARCHAR(64) NOT NULL,            -- slug IMUTÁVEL; chave dentro de records.data
    name         VARCHAR(80) NOT NULL,            -- rótulo mutável
    type         column_type NOT NULL,
    position     SMALLINT NOT NULL,
    is_required  BOOLEAN NOT NULL DEFAULT FALSE,
    is_sensitive BOOLEAN NOT NULL DEFAULT FALSE,  -- RS05: redação em logs/notificações
    options      JSONB   NOT NULL DEFAULT '[]',   -- choices de 'select'
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT columns_unique_key      UNIQUE (table_id, key),
    CONSTRAINT columns_unique_position UNIQUE (table_id, position) DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT columns_select_has_options
        CHECK (type <> 'select' OR jsonb_array_length(options) > 0)
);
-- No máximo UMA coluna de vencimento por tabela (RF06)
CREATE UNIQUE INDEX columns_one_due_date_per_table
    ON columns (table_id) WHERE type = 'due_date';

-- =========================================================
-- records
-- =========================================================
CREATE TABLE records (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    table_id    UUID NOT NULL REFERENCES tables(id) ON DELETE CASCADE,
    user_id     UUID NOT NULL REFERENCES users(id)  ON DELETE CASCADE,  -- DESNORMALIZADO (nota 1)
    data        JSONB NOT NULL DEFAULT '{}',
    due_date    DATE,          -- PROMOVIDA da coluna type='due_date' (nota 2)
    position    INTEGER,       -- ordenação manual opcional (RF11)
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT records_data_is_object CHECK (jsonb_typeof(data) = 'object')
);
CREATE INDEX records_table_due_idx ON records (table_id, due_date ASC NULLS LAST);
CREATE INDEX records_due_scan_idx  ON records (due_date) WHERE due_date IS NOT NULL;  -- job de alertas
CREATE INDEX records_data_gin      ON records USING GIN (data jsonb_path_ops);        -- busca futura

-- =========================================================
-- alert_rules  (configuração; 1..N por tabela)
-- =========================================================
CREATE TABLE alert_rules (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    table_id     UUID NOT NULL REFERENCES tables(id) ON DELETE CASCADE,
    user_id      UUID NOT NULL REFERENCES users(id)  ON DELETE CASCADE,
    offset_days  SMALLINT NOT NULL CHECK (offset_days BETWEEN -365 AND 365),
                 -- 3 = avisa 3 dias ANTES; 0 = no dia; -1 = 1 dia DEPOIS (cobrança de atraso)
    channel      VARCHAR(16) NOT NULL DEFAULT 'in_app' CHECK (channel IN ('in_app','email')),
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT alert_rules_unique UNIQUE (table_id, offset_days, channel)
);

-- =========================================================
-- alerts  (instância disparada = notificação in-app)
-- =========================================================
CREATE TABLE alerts (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    record_id         UUID NOT NULL REFERENCES records(id)     ON DELETE CASCADE,
    rule_id           UUID NOT NULL REFERENCES alert_rules(id) ON DELETE CASCADE,
    user_id           UUID NOT NULL REFERENCES users(id)       ON DELETE CASCADE,
    trigger_date      DATE NOT NULL,   -- due_date - rule.offset_days
    due_date_snapshot DATE NOT NULL,   -- vencimento vigente quando o alerta nasceu
    status            VARCHAR(16) NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending','sent','read','dismissed','failed')),
    notified_at       TIMESTAMPTZ,
    read_at           TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- CHAVE DE IDEMPOTÊNCIA: o banco recusa alerta duplicado, não a aplicação
    CONSTRAINT alerts_idempotency UNIQUE (record_id, rule_id, trigger_date)
);
CREATE INDEX alerts_inbox_idx   ON alerts (user_id, status, trigger_date DESC);
CREATE INDEX alerts_pending_idx ON alerts (status, trigger_date) WHERE status = 'pending';
```

### Notas de modelagem (as decisões que importam)

1. **`records.user_id` desnormalizado.** Duplica `tables.user_id`. Custo: precisa ser preenchido no `save()` a partir da tabela-mãe (nunca do request). Benefício: a policy de RLS em `records` não precisa de subquery em `tables`, e o inbox de alertas indexa direto por usuário. Mesma lógica em `alert_rules` e `alerts`.

2. **`records.due_date` promovida.** Derivada no `save()` a partir de `data[<key da coluna due_date>]`. É a única forma de o job de alertas e a ordenação RF11 usarem índice B-tree. Fonte da verdade continua sendo o JSONB; a coluna é cache derivado, recalculado sempre que `data` ou a coluna `due_date` mudam.

3. **RF11 sai de graça.** `ORDER BY due_date ASC NULLS LAST` já produz exatamente a ordem pedida: vencidos (mais antigo primeiro) → vence hoje → próximos → futuros distantes → sem vencimento. Um único índice atende. A ordenação manual usa `ORDER BY position` quando o cliente pedir.

4. **RF10 é calculado, não armazenado.** Status de vencimento é anotação no queryset (`CASE WHEN due_date < :hoje THEN 'overdue' ...`), com `:hoje` = data corrente **no fuso do usuário** (`users.timezone`). Nada persistido → nada fica obsoleto à meia-noite.

5. **Idempotência dos alertas é do banco.** `UNIQUE (record_id, rule_id, trigger_date)` + `INSERT ... ON CONFLICT DO NOTHING`. Beat a cada 15 min, worker duplicado, retry de task — nenhum duplica notificação. `notified_at` sozinho não garante isso sob concorrência.

6. **Mudança de vencimento invalida alerta pendente.** Se `due_date` mudar, os `alerts` com `status='pending'` daquele registro são apagados no mesmo `save()`; o job os regera com o novo `trigger_date`. `due_date_snapshot` permite detectar/auditar.

7. **Janela de varredura.** O job não varre histórico infinito: `WHERE due_date BETWEEN :hoje - 30 days AND :hoje + max(offset_days)`.

8. **RLS com dois roles.** `remind_migrator` (dono das tabelas, roda `migrate`) e `remind_app` (runtime, sujeito às policies). Sem isso o dono da tabela ignora RLS silenciosamente — usar também `FORCE ROW LEVEL SECURITY`. A GUC `app.user_id` é setada com `SET LOCAL` dentro da transação do request (`ATOMIC_REQUESTS=True`) para não vazar entre conexões do pool.

---

## Phases

### Phase 0 — Scaffold e infraestrutura local
**Objective:** `docker compose up` sobe web+db+redis+worker+beat e responde em `/api/health/`.

**Steps:**
1. `django-admin startproject config .`; settings dividido em `base/dev/prod` com `python-decouple`.
2. `docker-compose.yml` com serviços `web`, `db` (postgres:16, extensões `citext` + `pgcrypto`), `redis`, `worker`, `beat`.
3. `requirements/base.txt` conforme seção 12 da stack + `drf-spectacular`, `pytest-django`, `factory-boy`, `freezegun`.
4. App `core` com `TimeStampedUUIDModel` (abstract: `id` UUID PK, `created_at`, `updated_at`) e endpoint de health.
5. `.env.example`, `.gitignore`, `Makefile` (`make up`, `make test`, `make migrate`). `git init`.

**Files Touched:** `config/settings/base.py`, `config/settings/dev.py`, `config/settings/prod.py`, `config/urls.py`, `config/celery.py`, `core/models.py`, `core/views.py`, `docker-compose.yml`, `Dockerfile`, `requirements/base.txt`, `.env.example`, `Makefile`
**Verify:** `docker compose up -d && curl -f http://localhost:8000/api/health/`
**Done When:** health retorna 200 e `docker compose ps` mostra os 5 serviços saudáveis.
**Time:** 3h

**Replanning triggers:**
- Postgres sem `citext`/`pgcrypto` na imagem → trocar `CITEXT` por `VARCHAR` + índice único em `lower(email)`.

---

### Phase 1 — `accounts`: usuário customizado e autenticação (RF01, RF02, RS03, RS07)
**Objective:** Cadastro, login JWT e proteção contra força bruta funcionando antes de qualquer dado de domínio existir.

**Steps:**
1. `User(AbstractBaseUser, PermissionsMixin)` com UUID PK, `email` como `USERNAME_FIELD`, `name`, `timezone`. Definir `AUTH_USER_MODEL` **antes** da primeira migration.
2. `PASSWORD_HASHERS` com `Argon2PasswordHasher` no topo; `AUTH_PASSWORD_VALIDATORS` ativos.
3. SimpleJWT: access 15 min, refresh 7 dias, `ROTATE_REFRESH_TOKENS=True`, `BLACKLIST_AFTER_ROTATION=True` (logout real — RS07).
4. Refresh token em cookie `httpOnly` + `Secure` + `SameSite=Lax`; access token só no corpo da resposta.
5. `django-axes` no login (5 tentativas / 15 min por IP+usuário).
6. Endpoints: `POST /api/auth/register/`, `/api/auth/login/`, `/api/auth/refresh/`, `/api/auth/logout/`, `GET|PATCH /api/auth/me/`.

**Files Touched:** `accounts/models.py`, `accounts/managers.py`, `accounts/serializers.py`, `accounts/views.py`, `accounts/urls.py`, `accounts/tests/test_auth.py`, `config/settings/base.py`
**Verify:** `pytest accounts/ -v`
**Done When:** registro→login→refresh→logout passam; senha no banco começa com `argon2$`; 6ª tentativa errada retorna 429 (axes 7 usa Too Many Requests, não 403).
**Time:** 4h

**Replanning triggers:**
- Se o cookie httpOnly atrapalhar a browsable API, expor também modo Bearer puro em `dev`.

---

### Phase 2 — `tables`: tabelas e colunas dinâmicas (RF03, RF04, RF05, RF06)
**Objective:** Usuário define a estrutura da tabela; o banco rejeita definições inválidas, não só o serializer.

**Steps:**
1. Models `Table` e `Column` exatamente como o DDL (incluindo o `UniqueConstraint` parcial de `due_date` e o `CheckConstraint` de `select`).
2. Geração do `key` no `Column.save()` a partir de `name` (slugify + sufixo numérico em colisão); **imutável** após criação — serializer rejeita alteração.
3. `TableViewSet` e `ColumnViewSet` aninhado em `/api/tables/{table_id}/columns/`, com `get_queryset()` **sempre** filtrado por `self.request.user`.
4. `PATCH /api/tables/{id}/columns/reorder/` para `position` em lote (constraint DEFERRABLE permite a permutação numa transação).
5. ~~Exclusão de coluna faz purge da chave nos registros.~~ **ADIADO PARA A PHASE 3** — a tabela `records` só existe lá. Ver "Dívida carregada" abaixo.

**Files Touched:** `tables/models.py`, `tables/serializers.py`, `tables/views.py`, `tables/urls.py`, `tables/tests/test_tables.py`, `tables/tests/test_columns.py`
**Verify:** `pytest tables/ -v`
**Done When:** criar 2ª coluna `due_date` na mesma tabela → 400; `GET /api/tables/{id_de_outro_user}/` → 404; reorder persiste.
**Time:** 5h

**Dívida carregada para a Phase 3:**
- `UPDATE records SET data = data - :key WHERE table_id = :id` ao excluir uma coluna. Sem isso o JSONB acumula chaves órfãs, que reaparecem no CSV (RF13) e inflam o índice GIN. Entra como `perform_destroy` no `ColumnViewSet` assim que o model `Record` existir, com teste.
- Decisão tomada aqui e que a Phase 3 herda: `type` de coluna é **imutável**. Alterar o tipo deixaria registros já gravados com valores que não passam mais na validação — corrupção silenciosa. Para trocar, apague e recrie a coluna.

**Replanning triggers:**
- Se o `UniqueConstraint` parcial conflitar com o reorder → `bulk_update` dentro de `transaction.atomic` com `SET CONSTRAINTS ALL DEFERRED`.

---

### Phase 3 — `records`: registros JSONB validados por schema (RF07, RF08, RF09)
**Objective:** CRUD de registros com payload validado contra a definição de colunas da tabela.

**Steps:**
1. Model `Record` conforme DDL. `save()` deriva `due_date` de `data[due_key]` e preenche `user_id` a partir de `self.table.user_id` (nunca do request).
2. `RecordDataValidator`: carrega as colunas da tabela e valida/coerciona cada chave —
   `text`→str+max_length · `number`→Decimal · `date`/`due_date`→ISO `YYYY-MM-DD` · `datetime`→ISO 8601 · `boolean`→bool · `email`→`EmailValidator` · `select`→valor ∈ `options`.
   Chave desconhecida → 400. `is_required` vazio → 400.
3. `RecordViewSet` aninhado em `/api/tables/{table_id}/records/`, queryset filtrado por `user` **e** `table_id`.
4. Paginação (`PageNumberPagination`, 50) e `select_related('table')` para evitar N+1.
5. Invalidação de alertas pendentes quando `due_date` muda (nota 6 do modelo) — implementado como hook, ativado na Phase 5.

**Files Touched:** `records/models.py`, `records/validators.py`, `records/serializers.py`, `records/views.py`, `records/urls.py`, `records/tests/test_records_crud.py`, `records/tests/test_data_validation.py`
**Verify:** `pytest records/ -v`
**Done When:** payload com chave inexistente → 400; `select` fora de `options` → 400; após salvar, `records.due_date` reflete o valor do JSONB.
**Time:** 6h

**Replanning triggers:**
- Se a validação por linha ficar lenta em lote, cachear a definição de colunas por `table_id` no serializer (uma query por request).

---

### Phase 4 — Vencimento: status e ordenação (RF10, RF11)
**Objective:** Listagem devolve o estado de vencimento já calculado e ordenado, respeitando o fuso do usuário.

**Steps:**
1. `RecordQuerySet.with_due_status(today)`: anotação `Case/When` → `overdue | due_today | due_soon | on_track | no_due`, usando `table.alert_lead_days` como limiar de `due_soon`.
2. `today` via `timezone.localdate(timezone=ZoneInfo(request.user.timezone))` — nunca `date.today()`.
3. Ordenação padrão `due_date ASC NULLS LAST, created_at ASC`; `?ordering=position|-due_date|created_at` via `OrderingFilter` com allow-list.
4. Filtro `?status=overdue,due_today` via `django-filter`.
5. Testes com `freezegun` cobrindo virada de dia e usuário em fuso diferente do servidor.

**Files Touched:** `records/managers.py`, `records/filters.py`, `records/views.py`, `records/tests/test_due_status.py`, `records/tests/test_ordering.py`
**Verify:** `pytest records/tests/test_due_status.py records/tests/test_ordering.py -v`
**Done When:** com data congelada os 5 status saem corretos e a ordem é vencidos→hoje→próximos→futuros→sem data.
**Time:** 4h

**Replanning triggers:**
- Se `alert_lead_days` precisar ser por coluna em vez de por tabela → mover o campo para `columns` e reabrir Phase 2.

---

### Phase 5 — `alerts`: regras, job Celery e inbox (RF12)
**Objective:** Job periódico gera notificações sem nunca duplicar; usuário lê/descarta pelo inbox.

**Steps:**
1. Models `AlertRule` e `Alert` conforme DDL, incluindo `alerts_idempotency`.
2. Ao criar tabela com coluna `due_date`, criar `AlertRule` padrão (`offset_days = table.alert_lead_days`, `channel='in_app'`).
3. Task `scan_due_records()`:
   - varre `records ⋈ alert_rules` na janela `[hoje-30d, hoje+max(offset_days)]`;
   - `trigger_date = due_date - offset_days`; seleciona `trigger_date <= hoje`;
   - `bulk_create(..., ignore_conflicts=True)` → `ON CONFLICT DO NOTHING`;
   - marca `status='sent'`, `notified_at=now()` para o canal `in_app`;
   - agrupa por usuário para usar o fuso correto no cálculo de `hoje`.
4. Celery Beat a cada 15 min (`CELERY_BEAT_SCHEDULE`).
5. Endpoints: `GET /api/alerts/` (inbox filtrado por `request.user`), `POST /api/alerts/{id}/read/`, `POST /api/alerts/{id}/dismiss/`, CRUD em `/api/tables/{id}/alert-rules/`.
6. Payload do alerta carrega **apenas** `table_name`, `due_date` e um rótulo do registro — nunca o `data` completo, nunca colunas com `is_sensitive=True` (RS05).

**Files Touched:** `alerts/models.py`, `alerts/tasks.py`, `alerts/services.py`, `alerts/serializers.py`, `alerts/views.py`, `alerts/urls.py`, `config/celery.py`, `alerts/tests/test_scan_task.py`, `alerts/tests/test_idempotency.py`, `alerts/tests/test_inbox.py`
**Verify:** `pytest alerts/ -v`
**Done When:** rodar `scan_due_records()` 3× seguidas produz exatamente 1 alerta por `(record, rule, trigger_date)`; alterar `due_date` regenera o alerta pendente com nova data; serialização do alerta não contém coluna sensível.
**Time:** 7h

**Replanning triggers:**
- Se a varredura passar de ~200 ms com 100k registros → trocar o `NOT EXISTS` por SQL bruto `INSERT ... SELECT ... ON CONFLICT DO NOTHING` (uma única ida ao banco).

---

### Phase 6 — `exports`: CSV seguro (RF13, RS08)
**Objective:** Download de CSV reutilizando a queryset autorizada, sem risco de injeção de fórmula.

**Steps:**
1. `GET /api/tables/{id}/export/` reusando `RecordViewSet.get_queryset()` — nada de query separada.
2. `StreamingHttpResponse` + `csv.writer` sobre `.iterator(chunk_size=500)`.
3. Cabeçalhos na ordem de `columns.position`; valores lidos de `data[key]`.
4. **Sanitização de CSV injection:** prefixar `'` em células iniciadas por `=`, `+`, `-`, `@`, TAB ou CR (RS08).
5. `Content-Disposition` com nome de arquivo sanitizado; log registra apenas `table_id` e contagem de linhas, nunca conteúdo.

**Desvio:** o endpoint ficou em `/api/tables/{id}/records/export/` como *action* do `RecordViewSet`, não em `/api/tables/{id}/export/` com view própria. Motivo: RS08 pede que a exportação reuse a queryset autorizada da listagem — uma action reusa `get_queryset()` por construção, enquanto uma `APIView` separada refaria a busca da tabela e seria um segundo lugar onde esquecer o filtro por dono.

**Files Touched:** `exports/services.py`, `exports/csv_safety.py`, `records/views.py`, `exports/services.py`, `exports/urls.py`, `exports/tests/test_export.py`
**Verify:** `pytest exports/ -v`
**Done When:** export de tabela alheia → 404; célula `=SUM(A1)` sai como `'=SUM(A1)`; ordem das colunas bate com `position`.
**Time:** 3h

**Replanning triggers:**
- Nenhum previsto; fase isolada.

---

### Phase 7 — Row-Level Security e endurecimento (RS01, RS05, RS06, RS07)
**Objective:** Segunda barreira no banco, mais higiene de logs e headers.

**Steps:**
1. Migration `RunSQL` criando roles `remind_migrator` (owner) e `remind_app` (runtime, `NOSUPERUSER NOBYPASSRLS`).
2. `ENABLE` + `FORCE ROW LEVEL SECURITY` e policies `USING (user_id = current_setting('app.user_id', true)::uuid)` em `tables`, `records`, `alert_rules`, `alerts`; `columns` via policy com `EXISTS` em `tables`.
3. `ATOMIC_REQUESTS = True` + middleware `SetCurrentUserMiddleware` executando `SET LOCAL app.user_id = %s`; hook equivalente em `alerts/tasks.py` (por usuário, dentro de `transaction.atomic`).
4. `RedactingFilter` no logging: bloqueia `password`, `token`, `authorization`, o `data` de records e qualquer coluna `is_sensitive`.
5. Settings de produção: `DEBUG=False`, `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS`, `ALLOWED_HOSTS` explícito, `django-cors-headers` com allow-list.

**Files Touched:** `core/migrations/0002_rls_policies.py`, `core/middleware.py`, `core/logging.py`, `config/settings/prod.py`, `core/tests/test_rls.py`
**Verify:** `pytest core/tests/test_rls.py -v && python manage.py check --deploy --settings=config.settings.prod`
**Done When:** teste que roda `Record.objects.all()` **sem** filtro por usuário, conectado como `remind_app` com `app.user_id` de A, retorna zero linhas de B; `check --deploy` sem issues.
**Time:** 6h

**Replanning triggers:**
- Se RLS quebrar migrations ou o Django Admin → isolar `remind_app` só no runtime e documentar. Se ainda assim travar, RLS vira Phase 7b opcional e o isolamento fica só no queryset — registrar a regressão explicitamente no README.

---

### Phase 8 — Suite de segurança do MVP (seção 10 da especificação)
**Objective:** Cada um dos 10 critérios de segurança do MVP tem um teste que falha se a proteção sumir.

**Steps:**
1. `conftest.py` com fixtures `user_a`, `user_b` e tabelas/registros de cada um.
2. Teste parametrizado de *cross-tenant* sobre todos os endpoints: A tentando GET/PATCH/DELETE recurso de B → **404** (nunca 403, para não confirmar existência).
3. Teste de que todo endpoint sob `/api/` (exceto auth e health) retorna 401 sem token.
4. Testes de hash de senha, export autenticado, e de que o log de request não contém valor de coluna sensível (`caplog`).
5. `pytest-cov` com gate em 85% nos apps de domínio.

**Files Touched:** `conftest.py`, `tests/security/test_cross_tenant.py`, `tests/security/test_auth_required.py`, `tests/security/test_logging_redaction.py`, `pytest.ini`
**Verify:** `pytest -v --cov=. --cov-fail-under=85`
**Done When:** os 10 checkboxes da seção 10 têm teste correspondente e a suite passa.
**Time:** 5h

**Replanning triggers:**
- Cobertura abaixo de 85% por código de infraestrutura → excluir `config/` e `*/migrations/` do cálculo antes de baixar o gate.

---

### Phase 9 — Documentação e superfície mínima de uso
**Objective:** Alguém clona o repo e exercita tudo sem frontend.

**Steps:**
1. `drf-spectacular` em `/api/docs/` (Swagger UI) e `/api/schema/`.
2. Django Admin registrando `Table`, `Column`, `Record`, `AlertRule`, `Alert` (`data` somente leitura).
3. `README.md`: setup em 5 comandos, mapa RF/RS → onde está implementado, diagrama ER (Mermaid).
4. `docs/data-model.md`: o DDL e as 8 notas de modelagem desta seção, como documento vivo.
5. `manage.py seed_demo`: usuário demo + tabela "Contratos" do exemplo da seção 7 da especificação.

**Files Touched:** `config/urls.py`, `tables/admin.py`, `records/admin.py`, `alerts/admin.py`, `README.md`, `docs/data-model.md`, `core/management/commands/seed_demo.py`
**Verify:** `docker compose up -d && python manage.py seed_demo && curl -f http://localhost:8000/api/schema/`
**Done When:** `/api/docs/` lista todos os endpoints; seed cria a tabela Contratos com 3 registros e status de vencimento corretos.
**Time:** 3h

---

## Dependencies & Assumptions

- Phase 1 **precede** todas as migrations de domínio (`AUTH_USER_MODEL` não muda depois sem recriar o banco).
- Phase 7 (RLS) depende de todos os models existirem — não antecipar.
- Phases 4 e 6 dependem da Phase 3; Phase 5 depende da Phase 4 (`due_date` promovido).
- Assume Postgres ≥ 14 (`gen_random_uuid()` nativo, `jsonb_path_ops`, `FORCE ROW LEVEL SECURITY`).
- Assume uma tabela pertence a exatamente um usuário. Compartilhamento de tabelas trocaria o `user_id` desnormalizado por uma tabela de membership → replanejar Phases 2, 3 e 7.

## Current State

Diretório vazio (`c:/Users/Nova Peças/Desktop/Projetos/remind-task`), sem git inicializado. Especificações em `stack-tecnologica-django.md` e `sistema-alertas.md` (anexos — copiar para `docs/` na Phase 0).

## Notes

- **Desvio deliberado da especificação:** a entidade `RecordValue` (seção 6 do documento conceitual) foi substituída por `records.data JSONB` + `records.due_date`. Justificativa completa na seção **Modelo de dados**. Registrar como ADR-0001 do projeto.
- **Adições ao modelo conceitual:** `AlertRule` (a spec não previa configuração de antecedência), `columns.key` imutável, `columns.is_sensitive`, `users.timezone`, `records.position`, `alerts.due_date_snapshot`.
- **Storage:** o projeto está no disco interno (`Desktop/Projetos/`), fora de `${DEV_ROOT}`. Se o volume interno apertar, mover para `${DEV_ROOT}/Desenvolvimento/remind-task` antes da Phase 0.
- **Total estimado:** ~46h (≈6 dias de trabalho focado).
