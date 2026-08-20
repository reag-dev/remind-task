# Plan: remind-task — Frontend SPA

**Date:** 2026-08-20
**Status:** Phases 0-3 concluídas em 2026-08-20; Phases 4-8 pendentes
(plano revisto em 2026-08-20: TanStack Table adotado, paginação promovida a fase própria)
**Stack:** React 19 + Vite + TypeScript + TanStack Query + TanStack Table + React Router
**Plano irmão:** [`remind-task-mvp-2026-08-19.md`](remind-task-mvp-2026-08-19.md) (backend, concluído)

## Goal

Entregar a interface que a especificação pressupõe na seção 9 (`Frontend → API/Backend`),
consumindo a API REST existente. O alvo é o que a seção 12 descreve: alguém abre a tela e
**vê imediatamente o que está vencendo**.

## Estado atual (o que já existe)

Backend completo e sob teste — 383 provas, cobertura 92,69%, RF01–RF13 e RS01–RS08
implementados. A API está fechada e documentada em `/api/schema/`. Nada de frontend
existe ainda: `frontend/` não existe, `package.json` não existe.

**O backend já foi provisionado para uma SPA separada** — não é suposição:

| Evidência | Arquivo |
|---|---|
| `CORS_ALLOWED_ORIGINS=http://localhost:3000` | `.env.example` |
| `CORS_ALLOW_CREDENTIALS = True` | `config/settings/base.py:226` |
| `corsheaders` no `INSTALLED_APPS` e primeiro no `MIDDLEWARE` | `config/settings/base.py:36,53` |
| Refresh em cookie httpOnly com `AUTH_COOKIE_SECURE=False` no dev | `config/settings/dev.py` |
| "O access token continua no corpo — mantido em memória pelo cliente" | `accounts/cookies.py` |

Node v24.13.1 e npm 11.8.0 disponíveis na máquina.

## Scope

### In-Scope
- SPA em `frontend/`, servida pelo Vite em `:3000`, consumindo `http://localhost:8000/api/`.
- Auth completa: registro, login, refresh silencioso, logout, rotas protegidas.
- CRUD de tabelas, colunas (7 tipos) e registros.
- Grid dinâmico sobre **TanStack Table**, com indicadores de vencimento (RF10).
- **Paginação, ordenação e filtragem server-side** compartilhadas por registros, tabelas e
  alertas — fase própria, não um detalhe da tela de registros.
- Caixa de entrada de alertas + regras de antecedência por tabela (RF12).
- Download de CSV autenticado (RF13).
- Testes de componente/integração com Vitest + Testing Library + MSW.
- Serviço `frontend` no `docker-compose.yml` e CI rodando back + front.
- **Duas mudanças pontuais de backend**, ambas de transporte e nenhuma de contrato de
  recurso: `CORS_EXPOSE_HEADERS` (Phase 7) e uma classe de paginação com `page_size`
  limitado (Phase 5).

### Out-of-Scope
- **SSR / Next.js.** Ver "Decisão de stack".
- Virtualização de linhas (`@tanstack/react-virtual`). Com 50–200 linhas por página não há
  o que virtualizar; entra se e quando a medição pedir.
- Redimensionar, fixar e agrupar colunas. São recursos de planilha, não do MVP.
- Deploy, CDN, domínio, build de produção servido por nginx.
- Design system próprio, tema escuro, i18n (pt-BR fixo, como o backend).
- Realtime/WebSocket para alertas — a inbox é buscada por polling/refetch.
- Reordenar registros por drag-and-drop. A spec pede "alterar a ordenação manualmente",
  o que `?ordering=` já satisfaz.

---

## Decisão de stack

**React + Vite + TypeScript.** Alternativas consideradas e por que caíram:

| Alternativa | Por que não |
|---|---|
| **Next.js** | SSR não tem o que renderizar aqui: toda a tela é privada, o access token vive na memória do browser e o refresh está num cookie preso a `path=/api/auth/` na origem da API — um servidor Next não alcança nenhum dos dois. Pagaria-se um segundo processo para renderizar telas de loading. |
| **Django templates + HTMX** | Genuinamente menor: sem toolchain Node, sem CORS, sem JWT no browser (usaria sessão). Cai por dois motivos concretos — a API JWT é o entregável do projeto e ficaria sem consumidor real; e as telas de coluna/registro são estado de formulário dinâmico derivado de `column.type`, que é exatamente onde HTMX obriga a reconstruir estado no servidor a cada interação. |
| **Vue / Svelte** | Empate técnico. React ganha por ser o que o ecossistema de datagrid e a geração de tipos OpenAPI atendem melhor. |

### Datagrid: TanStack Table

A versão anterior deste plano dispensava biblioteca de datagrid, com o argumento de que
`<table>` + `columns.map()` bastava. **O argumento estava mal colocado.** Ele mediu o custo
de *renderizar* a tabela, que de fato é baixo, e ignorou o custo de *coordenar o estado*
dela — que é onde o trabalho realmente está assim que a Phase 5 entra:

- `sorting`, `columnFilters` e `pagination` viram três estados que precisam andar juntos,
  virar query string, sobreviver ao refetch do TanStack Query e voltar da URL num F5.
- Mudar filtro tem de resetar `pageIndex` para 0. Esquecer isso deixa o usuário na página 7
  de um resultado com 2 páginas, vendo uma lista vazia — o bug clássico de paginação
  escrita à mão.
- As colunas são definidas em tempo de execução a partir de `table.columns`, então o
  modelo de colunas é dado, não código. É precisamente o formato que o `columnHelper`
  consome.

TanStack Table é headless — dá o estado e os modelos, não o HTML. O `<table>` continua
sendo nosso, o CSS continua sendo nosso, e nada do que foi descartado acima (virtualização,
resize, agrupamento) entra junto. É a peça certa pelo motivo certo.

**Condição inegociável: modo manual.** Este backend pagina, ordena e filtra no Postgres.
A tabela precisa nascer com `manualPagination`, `manualSorting` e `manualFiltering` em
`true`, e receber `rowCount` do `count` da resposta. Sem isso o TanStack assume que recebeu
o conjunto inteiro e passa a paginar e ordenar **as 50 linhas que estão na memória** — a
UI fica plausível, os números batem, e a lista mente. Ver armadilha 8.

**Tipos gerados, não escritos à mão.** `openapi-typescript` contra `/api/schema/`. O schema
já está sob teste (`core/tests/test_schema.py` roda `spectacular --fail-on-warn`), então os
tipos gerados são confiáveis, e um diff no arquivo gerado denuncia mudança de contrato antes
do runtime.

---

## Contrato da API (o que o frontend consome)

Base: `http://localhost:8000/api/`.

```
POST   /auth/register/                     {email,name,timezone,password} -> 201 user
POST   /auth/login/                        {email,password} -> {access, user} + Set-Cookie refresh
POST   /auth/refresh/                      (cookie) -> {access} + Set-Cookie refresh rotacionado
POST   /auth/logout/                       (cookie) -> 204
GET    /auth/me/  PATCH /auth/me/          -> {id,email,name,timezone,created_at}

GET|POST         /tables/                  {name,description,alert_lead_days}
GET|PATCH|DELETE /tables/{id}/             inclui `columns[]` embutido
GET|POST         /tables/{tid}/columns/    {name,type,is_required,is_sensitive,options[]}
PATCH|DELETE     /tables/{tid}/columns/{id}/
PATCH            /tables/{tid}/columns/reorder/   {order:[uuid,...]}  <- TODOS os ids

GET|POST         /tables/{tid}/records/    {data:{<key>:valor}}
GET|PATCH|DELETE /tables/{tid}/records/{id}/
GET              /tables/{tid}/records/export/?delimiter=,|;
        filtros: ?status=overdue,due_today  ?due_before=  ?due_after=  ?has_due_date=
        ordem:   ?ordering=due_date|created_at|updated_at|position  (prefixo `-` inverte)

GET              /alerts/?status=            POST /alerts/{id}/read/   POST /alerts/{id}/dismiss/
GET|POST         /tables/{tid}/alert-rules/  {offset_days,channel,is_active}
PATCH|DELETE     /tables/{tid}/alert-rules/{id}/
```

`ColumnType`: `text` · `number` · `date` · `datetime` · `boolean` · `email` · `select` · `due_date`
`DueStatus`:  `overdue` · `due_today` · `due_soon` · `on_track` · `no_due`

### Paginação

`PageNumberPagination` do DRF, `PAGE_SIZE = 50`, aplicada a **toda** listagem —
`/tables/`, `/records/` e `/alerts/`. Formato da resposta:

```json
{ "count": 137, "next": "http://…/records/?page=3", "previous": "http://…/records/?page=1",
  "results": [ … ] }
```

Como isso mapeia para o TanStack Table:

| TanStack | Origem |
|---|---|
| `pagination.pageIndex` | `page - 1` — a API é 1-based, a tabela é 0-based |
| `pagination.pageSize` | `page_size` (Phase 5) ou o 50 fixo |
| `rowCount` | `count` da resposta |
| `pageCount` | derivado por `Math.ceil(count / pageSize)` — não enviar os dois |

A navegação é por `?page=N` calculado do `pageIndex`, **não** por seguir as URLs de
`next`/`previous`. Elas são absolutas e apontam para o host da API; usá-las obrigaria o
cliente a reparsear query string alheia, e o TanStack entrega índice, não cursor. Ficam
úteis para uma coisa só: saber que existe página seguinte quando `count` ainda não chegou.

Página fora do intervalo responde **404**, não lista vazia. É o mesmo 404 de recurso
inexistente, e precisa de tratamento próprio na paginação (voltar para a página 1) para
não virar "tabela não encontrada" na tela.

---

### Dez armadilhas que este backend impõe ao cliente

1. **Recarregar a página perde o login.** O access token nunca é persistido (decisão do
   `accounts/cookies.py`). O bootstrap da aplicação é `POST /auth/refresh/` com
   `credentials: "include"`, e só depois de resolver é que as rotas decidem redirecionar.
   Renderizar a tela de login antes dessa resposta faz o usuário logado piscar para fora.
2. **Refresh rotaciona e coloca o anterior na blacklist** (`ROTATE_REFRESH_TOKENS` +
   `BLACKLIST_AFTER_ROTATION`). Se três requisições tomarem 401 juntas e cada uma disparar
   seu refresh, a segunda e a terceira usam um token já queimado → 401 → logout. O
   interceptor precisa de **single-flight**: uma promessa compartilhada, as demais esperam.
   É o bug número um desse desenho de auth.
3. **`credentials: "include"` em toda chamada a `/auth/`.** Sem isso o cookie não vai e o
   refresh responde 401 com "Refresh token ausente." O cookie tem `path=/api/auth/`, então
   as rotas de dados não o recebem — e não devem.
4. **CSV não é `<a href>`.** A rota exige `Authorization: Bearer`, e um `href` não carrega
   header. É `fetch` → `blob` → `URL.createObjectURL` → âncora temporária → `revokeObjectURL`.
5. **`Content-Disposition` não é legível por JS cross-origin** sem `Access-Control-Expose-Headers`.
   Ausente hoje. Tratado na Phase 7.
6. **Recurso alheio responde 404, nunca 403** (RS04, deliberado). O tratamento de erro do
   cliente não pode transformar 404 em "sem permissão" — isso reintroduz no frontend o
   vazamento que o backend gastou uma suíte para evitar.
7. **Login bloqueado pelo django-axes.** ✅ **Resolvido na Phase 1, medido contra a API.**
   É **429** — o `@extend_schema` da `LoginView` estava certo e o comentário do
   `LoginSerializer` sobre "403 de lockout" está desatualizado (ver pendências no fim).
   Dois detalhes que só a medição deu: o bloqueio cai já **na quinta** tentativa, não
   depois dela; e o corpo vem em **texto puro e em inglês** ("Account locked: too many
   login attempts."), não em JSON, porque é o `AxesMiddleware` respondendo antes do DRF.
   Tratado em `auth/mensagens.ts`, com teste em `routes/Login.test.tsx`.
8. **TanStack Table em modo automático mente.** O padrão da biblioteca é assumir que o
   array recebido é o conjunto completo. Com `?page=1` na mão, `getPaginationRowModel()`
   pagina as 50 linhas em memória e `getSortedRowModel()` ordena só elas: o rodapé diz
   "página 1 de 1" com 137 registros no banco, e ordenar por vencimento reordena um
   recorte arbitrário. Nenhum erro é lançado. `manualPagination`, `manualSorting` e
   `manualFiltering` em `true`, mais `rowCount`, são obrigatórios — e a Phase 5 tem teste
   dedicado a isso, porque é uma regressão que passa despercebida em revisão.
9. **Ordenar por um campo só quebra a paginação.** O `NullsLastOrderingFilter` faz
   `queryset.order_by(*ordering)` com exatamente o que veio na query string. O default do
   `RecordViewSet` é `["due_date", "created_at"]`, que tem desempate — mas `?ordering=due_date`
   **substitui** o default por uma chave só. Registros com o mesmo vencimento ficam em ordem
   indefinida entre uma requisição e outra, e a mesma linha pode aparecer em duas páginas ou
   em nenhuma. A correção é do cliente e é barata: **sempre anexar `created_at` como último
   termo** (`?ordering=due_date,created_at`). `created_at` já está em `ordering_fields`.
10. **Não existe `page_size` hoje.** `PageNumberPagination` sem `page_size_query_param` ignora
    o parâmetro em silêncio. Um seletor de "linhas por página" ligado ao `pageSize` do
    TanStack pareceria funcionar — a tabela mudaria de estado, a API devolveria 50 assim
    mesmo, e a contagem de páginas ficaria errada. Ou o seletor não existe, ou o backend
    ganha o parâmetro. A Phase 5 escolhe a segunda.

---

## Phases

### Phase 0 — Andaime e contrato tipado

**Objective:** `npm run dev` sobe em `:3000`, fala com a API e os tipos vêm do schema.

- Vite + React + TS em `frontend/`, sem CRA e sem framework de UI pesado.
- `openapi-typescript` gerando `src/api/schema.d.ts` a partir de `/api/schema/`, via script
  `npm run api:types`. O arquivo é **commitado** — é ele que torna a mudança de contrato
  visível no diff.
- Cliente `fetch` fino em `src/api/client.ts` (sem axios: `fetch` nativo resolve, e o
  interceptor da Phase 1 é código nosso de qualquer forma).
- `.env` do front: `VITE_API_URL=http://localhost:8000/api`.
- ESLint + Prettier + `tsc --noEmit`, espelhando a disciplina do `ruff.toml`.

**Files Touched:**
`frontend/package.json` · `frontend/vite.config.ts` · `frontend/tsconfig.json` ·
`frontend/eslint.config.js` · `frontend/.env.example` · `frontend/index.html` ·
`frontend/src/main.tsx` · `frontend/src/api/client.ts` · `frontend/src/api/schema.d.ts` ·
`.gitignore` (node_modules, dist)

**Verify:**
```bash
cd frontend && npm ci && npm run api:types && npm run typecheck && npm run build
```

---

### Phase 1 — Autenticação

**Objective:** login, F5 sem perder sessão, logout, rota protegida.

- `AuthProvider` com `accessToken` em `useState` (nunca `localStorage` — o motivo está
  documentado em `accounts/cookies.py` e vale para o cliente).
- Bootstrap: `POST /auth/refresh/` no mount; enquanto pendente, um estado `"carregando"`
  distinto de `"anônimo"`.
- Interceptor com **single-flight refresh** e fila de requisições em espera.
- Telas: `/login`, `/registro`. Erros de campo do DRF (`{"password": [...]}`) mapeados para
  o campo certo — o `RegisterSerializer` já os devolve assim de propósito.
- Confirmar o status real do lockout do axes e tratá-lo à parte do 401.
- `<RotaProtegida>` redirecionando para `/login` com `?next=`.

**Files Touched:**
`frontend/src/auth/AuthProvider.tsx` · `frontend/src/auth/useAuth.ts` ·
`frontend/src/auth/refresh.ts` · `frontend/src/routes/Login.tsx` ·
`frontend/src/routes/Registro.tsx` · `frontend/src/routes/RotaProtegida.tsx` ·
`frontend/src/api/client.ts`

**Verify:**
```bash
docker compose up -d && cd frontend && npm run dev
# login -> F5 -> continua logado; 6 senhas erradas -> mensagem de bloqueio, nao "senha invalida"
npm run test -- src/auth
```
O teste que segura a armadilha 2: três chamadas paralelas com token expirado disparam
**um** `POST /auth/refresh/`, verificado pelo contador do MSW.

---

### Phase 2 — Tabelas

**Objective:** listar, criar, renomear e excluir tabelas.

- TanStack Query como estado de servidor. Sem Redux/Zustand: o estado do app é quase todo
  remoto, e o pouco que é local (token, formulários) cabe em `useState`.
- Lista com nome, descrição, `alert_lead_days` e contagem de colunas.
- Exclusão com confirmação explícita nomeando a tabela — o backend apaga registros em
  cascata e a ação é irreversível.
- Erro 400 de nome duplicado exibido no campo.
- Paginação ainda não: a lista consome `results` e ignora `count`. A Phase 5 volta aqui e
  liga o componente compartilhado.

**Files Touched:**
`frontend/src/api/tables.ts` · `frontend/src/routes/Tabelas.tsx` ·
`frontend/src/routes/TabelaNova.tsx` · `frontend/src/components/DialogoConfirmar.tsx` ·
`frontend/src/App.tsx`

**Verify:**
```bash
cd frontend && npm run test -- src/routes/Tabelas && npm run typecheck
```

---

### Phase 3 — Colunas

**Objective:** configurar a estrutura dinâmica (RF05, RF06).

- Formulário com os 7 tipos; `options[]` só aparece para `select` e é obrigatório lá.
- `due_date`: desabilitar a opção quando a tabela já tem uma — o backend responde 400, mas
  oferecer a escolha para depois recusá-la é UI ruim.
- `type` imutável na edição (o serializer recusa a troca; a UI mostra o campo travado com
  o motivo).
- `is_sensitive` com o efeito real na Phase 4: valor mascarado por padrão.
- Reordenação por setas ↑↓ enviando `PATCH .../reorder/` com a lista **completa** de ids.
  Drag-and-drop fica fora — mesma chamada, dez vezes o código.
- Aviso na exclusão: apagar a coluna apaga a chave dela em todos os registros
  (`purge_column_key`), e apagar a de vencimento zera `due_date`.

**Files Touched:**
`frontend/src/api/columns.ts` · `frontend/src/routes/TabelaColunas.tsx` ·
`frontend/src/components/FormularioColuna.tsx` · `frontend/src/components/ListaColunas.tsx`

**Verify:**
```bash
cd frontend && npm run test -- src/routes/TabelaColunas
```

---

### Phase 4 — Grid dinâmico e CRUD de registros

**Objective:** RF07–RF10 na tela. Uma página de dados, sem paginação nem ordenação ainda.

- Modelo de colunas construído em runtime a partir de `table.columns` com `columnHelper`,
  já na ordem de `position`. `accessorFn: (row) => row.data[column.key]` — **`key`, não
  `name`**: o JSONB é indexado pelo slug, e `name` é só rótulo.
- Uma coluna extra, sem acessor, para o selo de status; e outra para as ações da linha.
- `cell` por tipo: `boolean` → ✓/✗, `date`/`due_date` → `dd/MM/yyyy`,
  `number` → `Intl.NumberFormat("pt-BR")`, `email` → `mailto:`, `select` → chip.
- `is_sensitive` → `••••••` com botão "revelar", que não persiste entre navegações nem
  entre páginas.
- Selo de status a partir de `due_status`, já vindo do serializer — **não recalcular no
  cliente**. A regra tem três implementações no backend (Python, SQL, predicado de filtro),
  todas amarradas por teste; uma quarta em TypeScript sairia de sincronia sem ninguém
  notar. Também não derivar de `days_until_due`, que é calculado da mesma fonte.
- Renderização: `getCoreRowModel()` e mais nada. Os modelos de ordenação, filtro e
  paginação **não** entram — são justamente os que a Phase 5 declara manuais.
- Formulário de registro montado a partir das colunas, respeitando `is_required`.

**Files Touched:**
`frontend/src/api/records.ts` · `frontend/src/routes/TabelaRegistros.tsx` ·
`frontend/src/components/GridRegistros.tsx` · `frontend/src/components/colunasDoGrid.tsx` ·
`frontend/src/components/CelulaValor.tsx` · `frontend/src/components/FormularioRegistro.tsx` ·
`frontend/src/components/SeloStatus.tsx`

**Verify:**
```bash
cd frontend && npm run test -- src/components/GridRegistros src/components/CelulaValor
```
Casos obrigatórios: os cinco `DueStatus` produzem selos distintos; coluna `is_sensitive`
não expõe o valor no DOM antes do clique em "revelar"; a célula lê `data[key]` e não
`data[name]`.

---

### Phase 5 — Paginação, ordenação e filtros server-side

**Objective:** o estado da tabela vira query string, e o Postgres faz o trabalho.

Fase própria porque é uma peça transversal, não um detalhe da tela de registros: o mesmo
componente serve `/tables/`, `/records/` e `/alerts/`, e é onde mora a armadilha 8.

- **Backend:** `core/pagination.py` com `PageNumberPagination` subclassada expondo
  `page_size_query_param = "page_size"` e `max_page_size = 200`. O teto não é decoração —
  sem ele, `?page_size=100000` transforma qualquer listagem em varredura de tabela, e as
  linhas carregam `data` JSONB inteiro. `DEFAULT_PAGINATION_CLASS` passa a apontar para ela.
  O `page_size` aparece no schema, o `npm run api:types` regenera e o diff prova que o
  detector de drift funciona.
- Hook `useTabelaServidor` guardando `{sorting, columnFilters, pagination}` num só lugar,
  serializando para query string e devolvendo os parâmetros do `useQuery`.
- `manualPagination: true`, `manualSorting: true`, `manualFiltering: true`, `rowCount: count`.
  Sem `getPaginationRowModel` nem `getSortedRowModel` no `useReactTable` — a ausência deles
  é a garantia estrutural de que a biblioteca não vai paginar em memória.
- Tradução do `sorting` do TanStack (`[{id, desc}]`) para `?ordering=`, **sempre anexando
  `created_at` como termo final** (armadilha 9). Só os campos de `ordering_fields` são
  ordenáveis; as colunas dinâmicas do JSONB não são, e o cabeçalho delas não recebe
  affordance de clique.
- `keepPreviousData` no TanStack Query: trocar de página mantém a tabela anterior visível
  em vez de piscar para vazio.
- Estado na URL (`?page=&ordering=&status=`), para que F5 e link compartilhado preservem a
  visão. É também o que faz o botão "voltar" do browser se comportar.
- **Resetar `pageIndex` para 0 em toda mudança de filtro ou de ordenação.** É a regressão
  mais provável desta fase.
- 404 de página fora do intervalo → voltar para a página 1, não propagar como erro de
  recurso.
- Barra de filtros: status multi-seleção (`?status=a,b`), `due_before`/`due_after`,
  `has_due_date`. Status inválido devolve 400 com mensagem de propósito
  (`RecordFilter.filter_status`) — exibir a mensagem, não engolir.
- Rodapé compartilhado: "N–M de `count`", navegação, seletor de linhas por página
  (25/50/100/200, limitado pelo `max_page_size`).

**Files Touched:**
`core/pagination.py` · `config/settings/base.py` · `core/tests/test_pagination.py` ·
`frontend/src/api/schema.d.ts` (regenerado) ·
`frontend/src/hooks/useTabelaServidor.ts` · `frontend/src/api/query.ts` ·
`frontend/src/components/Paginacao.tsx` · `frontend/src/components/FiltroStatus.tsx` ·
`frontend/src/components/GridRegistros.tsx` · `frontend/src/routes/TabelaRegistros.tsx` ·
`frontend/src/routes/Tabelas.tsx`

**Verify:**
```bash
docker compose exec web pytest core/tests/test_pagination.py -q
cd frontend && npm run api:types && git diff --exit-code src/api/schema.d.ts; echo "diff esperado: page_size"
npm run test -- src/hooks/useTabelaServidor src/components/Paginacao
```
Provas obrigatórias, cada uma cobrindo uma armadilha:
- backend: `?page_size=100000` devolve 200 linhas, não 100000;
- a tabela com 50 linhas e `count: 137` mostra **3 páginas**, não 1 (armadilha 8);
- clicar no cabeçalho de vencimento emite `?ordering=due_date,created_at` (armadilha 9);
- mudar o filtro de status com `pageIndex=6` emite `?page=1`.

---

### Phase 6 — Alertas

**Objective:** RF12 na tela.

- `/alertas`: lista vinda de `GET /alerts/`, com `label`, `table_name`, `due_date`,
  `is_stale`, filtro por `status`, reusando a paginação da Phase 5.
- Ações "marcar como lido" e "descartar" com atualização otimista + rollback no erro.
- Badge de não lidos no cabeçalho (`?status=pending`), com `refetchInterval`. Sem WebSocket:
  o job roda uma vez por dia, então polling de minutos é folgado.
- Clique no alerta navega para o registro de origem.
- Regras de antecedência por tabela: CRUD de `offset_days` / `is_active`, com o 400 de
  duplicata exibido no campo. `channel` fixo em `in_app` — é o único implementado.
- `alert_lead_days` da tabela (limiar de `due_soon`) editável junto, explicando que é coisa
  diferente de `offset_days` (indicador visual vs. disparo de alerta).

**Files Touched:**
`frontend/src/api/alerts.ts` · `frontend/src/routes/Alertas.tsx` ·
`frontend/src/routes/TabelaRegras.tsx` · `frontend/src/components/BadgeAlertas.tsx`

**Verify:**
```bash
cd frontend && npm run test -- src/routes/Alertas
```

---

### Phase 7 — Exportação CSV

**Objective:** RF13 pelo browser, com o nome de arquivo que o backend escolheu.

- Backend: `CORS_EXPOSE_HEADERS = ["Content-Disposition"]` em `config/settings/base.py`.
  Sem isso o browser esconde o header e o arquivo baixa como `download`.
- Botão de export que **reusa os filtros e a ordenação da tela** — vem de graça do
  `useTabelaServidor`, e é o que a docstring de `RecordViewSet.export` promete (RS08).
  Uma exportação que ignora o filtro visível seria mentira de UI.
- **`page` e `page_size` são omitidos.** O export não pagina: ele transmite a queryset
  filtrada inteira. Mandar `?page=3` junto não quebra nada hoje, mas escreve na URL uma
  intenção que o servidor ignora.
- Seletor de delimitador `,` / `;`, com nota de que o Excel pt-BR espera `;`.
- Estado de carregando enquanto o blob chega; a resposta é streaming e pode demorar.

**Files Touched:**
`config/settings/base.py` · `frontend/src/api/export.ts` ·
`frontend/src/components/BotaoExportar.tsx` · `tests/security/test_export_authorization.py`

**Verify:**
```bash
docker compose exec web pytest tests/security/ -q
cd frontend && npm run test -- src/api/export
```
Acrescentar em `test_export_authorization.py` a prova de que `Content-Disposition` está
exposto — senão a linha de CORS pode sumir num refactor e o sintoma só aparece no browser.

---

### Phase 8 — Testes, acessibilidade e CI

**Objective:** o front nasce com a mesma disciplina do back.

- Vitest + Testing Library + MSW, com os handlers do MSW gerados a partir de
  `schema.d.ts` — mock que mente sobre o contrato é pior que nenhum mock. Os handlers de
  listagem **paginam de verdade**, devolvendo `count` maior que `results.length`; um mock
  que sempre devolve a lista completa esconderia exatamente a armadilha 8.
- Cobertura mínima em `vitest.config.ts`, espelhando o `fail_under = 85` do `.coveragerc`.
- Acessibilidade: navegação por teclado no grid, `aria-sort` nos cabeçalhos ordenáveis
  (alimentado pelo `sorting` do TanStack), `aria-live` no rodapé de paginação para anunciar
  a troca de página, e status de vencimento com texto além da cor — a spec pede
  "indicadores visuais", e cor sozinha não é indicador.
- Serviço `frontend` no `docker-compose.yml`, para `docker compose up` subir a stack inteira.
- **CI** (`.github/workflows/ci.yml`), pendência já levantada e nunca feita: job `backend`
  com `ruff check` + `pytest --cov`, job `frontend` com `typecheck` + `lint` + `test`.
  Um terceiro passo regenera os tipos e falha se o diff não for vazio — é o detector de
  drift entre schema e cliente.
- README: seção de frontend, e a de setup passando a subir os dois.

**Files Touched:**
`frontend/vitest.config.ts` · `frontend/src/test/setup.ts` · `frontend/src/test/handlers.ts` ·
`docker-compose.yml` · `.github/workflows/ci.yml` · `README.md` · `Makefile`

**Verify:**
```bash
cd frontend && npm run lint && npm run typecheck && npm run test -- --coverage
cd .. && docker compose up -d && curl -fsS http://localhost:3000 && docker compose exec web pytest -q
```

---

## Achados da implementação (Phases 0-1)

Registrados aqui porque mudam o que as fases seguintes podem assumir.

### `due_status` não é união no schema — é `string`

O gerador produz `TypeEnum` e `StatusEnum` como uniões, porque nascem de `choices` de campo
de modelo. Mas `due_status` é um `SerializerMethodField`, e o drf-spectacular não consegue
inferir escolhas de um método: sai `due_status: string`, com os cinco valores só em prosa no
`help_text`.

Consequência para a **Phase 4**, que ramifica em cima desse valor: a união está escrita à
mão em `api/tipos.ts`, e **a compilação não protege contra um sexto status**. Existe
`ehDueStatus()` para que a divergência apareça em runtime no ponto de entrada, em vez de
virar uma célula em branco no meio do grid.

Correção possível no backend, **não feita** porque está fora do escopo declarado:
`@extend_schema_field(serializers.ChoiceField(choices=DueStatus.choices))` sobre
`get_due_status`. Isso tornaria o schema honesto para qualquer consumidor, inclusive quem
lê `/api/docs/`. Decisão do dono do projeto.

### TypeScript 7 não serve para esta toolchain

`npm install -D typescript` resolveu para **7.0.2**, o port nativo em Go, que exporta dois
símbolos e nenhuma API de compilador (`ts.factory` é `undefined`). O `openapi-typescript`
monta a saída pela AST factory e quebra com
`TypeError: Cannot read properties of undefined (reading 'createKeywordTypeNode')`.

Fixado em `typescript@^5` (resolveu 5.9.3). **Não desfixar** sem antes conferir se o
`openapi-typescript` já migrou — o sintoma aparece só no `npm run api:types`, não no build.

### `options` também sai como `unknown`, mas aqui a estreitagem é fato

Mesmo sintoma do `data`: `columns.options` é um `JSONField` e o schema diz `unknown`.
A diferença é que a forma **é** garantida — `ColumnSerializer.validate_options` recusa
não-lista, exige texto não vazio em cada item e rejeita repetidos; o default do modelo é
`list`, então nunca é nulo.

Estreitado para `string[]` em `api/tipos.ts`. Isso registra um fato do backend, ao contrário
do `data`, que continua `Record<string, unknown>` porque a forma dele só existe em tempo de
execução.

### Cobertura sem `include` se elogia sozinha

O provider v8 só relata arquivos que **algum teste importou**. Um módulo inteiro sem teste
nenhum não aparece na tabela, e a porcentagem sobe — o número passa a medir "o que testei do
que resolvi testar". Na Phase 2 isso escondia `Registro.tsx`, `RotaProtegida.tsx`,
`sessao.ts` e `Layout.tsx`.

Corrigido com `coverage.include: ["src/**/*.{ts,tsx}"]` no `vitest.config.ts`. No Vitest 3
isso se ligava com `all: true`; **a opção foi removida no Vitest 4** e o `include` assumiu o
papel — declarar `all` lá dá erro de tipo.

### `<dialog>` nativo não existe no jsdom

`HTMLDialogElement.prototype.showModal` é `undefined` no ambiente de teste. Há um stub em
`src/test/setup.ts`. O que ele **não** cobre, e portanto não está testado em lugar nenhum:
foco preso, `inert` no resto da página e `::backdrop` — que são justamente as razões de usar
`<dialog>` em vez de uma div. São comportamento de browser, verificáveis só em teste de
navegador de verdade.

### `erasableSyntaxOnly` proíbe parameter properties

O `tsconfig` liga a flag porque o Vite **apaga** tipos, não os transforma: sintaxe que
depende de emissão some no build. Isso barra `constructor(readonly x: T)` e enums — campos
declarados explicitamente, como em `ApiError`.

---

## O que dispara replanejamento

- **`@tanstack/react-table` instalar num major diferente do v8.** O plano assume a API v8
  (`useReactTable`, `getCoreRowModel`, `columnHelper`, `manualPagination`). Major novo →
  conferir os nomes antes da Phase 4; a decisão de arquitetura não muda, os identificadores
  sim.
- **O lockout do axes não é 429 nem 403** → a Phase 1 muda o tratamento e o backend pode
  precisar de ajuste no `@extend_schema`, que hoje está inconsistente com o código.
- **`openapi-typescript` não digerir o schema** (o `data` JSONB vira `unknown`; `oneOf` de
  `options`) → cai para tipos escritos à mão apenas para `Record`, mantendo o gerado para
  o resto. Não vale reescrever o schema do backend por causa do gerador.
- **A tela passar de ~300ms com 200 linhas por página** → entra `@tanstack/react-virtual`,
  que se acopla ao modelo de linhas já existente. É o caso em que a decisão desta revisão
  se paga: virtualizar uma tabela escrita à mão exigiria reescrevê-la.
- **A Phase 5 precisar de contagem por status para um painel** → hoje isso custa uma
  requisição por status. Com `page_size` disponível, `?status=overdue&page_size=1` já traz
  o `count` sem trafegar linhas — o incômodo some. Se ainda assim virar problema, o certo é
  `GET /api/tables/{id}/summary/` no backend, e ele **quebra**
  `tests/security/test_auth_required.py::test_every_api_route_is_classified` até ser
  classificado como protegido. O tripwire funcionando, não um problema.
- **Deploy em domínios de registrable domain diferentes** (ex.: `app.exemplo.com` +
  `api.outro.com`) → `AUTH_COOKIE_SAMESITE="Lax"` deixa de enviar o refresh e precisa virar
  `"None"` com `Secure`. Em dev não aparece: `localhost:3000` e `localhost:8000` são
  cross-origin mas **same-site**, então o Lax passa. É uma armadilha que só se manifesta
  no deploy — fora de escopo aqui, registrada para não surpreender lá.
