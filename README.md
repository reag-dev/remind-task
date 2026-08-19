# remind-task

Plataforma privada de **tabelas dinâmicas com controle de vencimentos**. O usuário cria tabelas com colunas configuráveis, marca uma coluna como data de vencimento, e o sistema gera alertas automáticos quando o prazo se aproxima.

Segurança é requisito central, não acessório: isolamento de dados por usuário em duas camadas (queryset + Row-Level Security no Postgres), Argon2id, UUID como identificador público e alertas idempotentes por constraint de banco.

| Camada | Tecnologia |
|---|---|
| API | Django 5 + Django REST Framework |
| Banco | PostgreSQL 16 |
| Auth | SimpleJWT + Argon2id + django-axes |
| Assíncrono | Celery + Celery Beat + Redis |
| Infra | Docker Compose |

---

## Setup

Requer apenas **Docker**. Não é preciso Python local.

```bash
cp .env.example .env          # ajuste DJANGO_SECRET_KEY se quiser
docker compose build
docker compose up -d
curl http://localhost:8000/api/health/
```

Resposta esperada: `{"status": "ok", "database": "up"}`

| Comando | O que faz |
|---|---|
| `make up` / `make down` | sobe / derruba a stack |
| `make logs` | logs de web, worker e beat |
| `make sh` | shell dentro do container web |
| `make migrate` | aplica migrations |
| `make test` | roda a suite (`pytest`) |
| `make reset` | **apaga o volume do Postgres** e sobe de novo |

Sem `make` no Windows: use `docker compose exec web <comando>` direto.

### Build falhando com `CERTIFICATE_VERIFY_FAILED`

Se o `docker compose build` morrer em `pip install` com:

```
SSL: CERTIFICATE_VERIFY_FAILED - unable to get local issuer certificate
```

seu antivírus ou proxy está fazendo inspeção TLS: ele reemite o certificado do
pypi.org com uma CA própria, que o Windows confia e o container não. Coloque a CA
em `docker/certs/*.crt` e rebuilde — instruções em
[`docker/certs/README.md`](docker/certs/README.md).

Não use `pip install --trusted-host`: isso desliga a verificação TLS.

### Superfície de uso

Não há frontend. A interface do MVP é:

- `http://localhost:8000/api/docs/` — Swagger UI (drf-spectacular)
- `http://localhost:8000/api/` — DRF Browsable API
- `http://localhost:8000/admin/` — Django Admin

---

## Documentação

| Documento | Conteúdo |
|---|---|
| [`docs/especificacao.md`](docs/especificacao.md) | Requisitos RF01–RF13 e RS01–RS08 |
| [`docs/data-model.md`](docs/data-model.md) | Schema vigente, diagrama ER e as decisões de modelagem |
| [`.claude/plans/remind-task-mvp-2026-08-19.md`](.claude/plans/remind-task-mvp-2026-08-19.md) | Plano de execução por fases |

---

## Estado atual

**Phases 0–3 concluídas** — infraestrutura, autenticação, estrutura dinâmica e registros.

| Phase | Escopo | Status |
|---|---|---|
| 0 | Scaffold, Docker Compose, health check | ✅ |
| 1 | `accounts` — usuário customizado, JWT, Argon2, axes | ✅ |
| 2 | `tables` — tabelas e colunas dinâmicas | ✅ |
| 3 | `records` — registros JSONB validados | ✅ |
| 4 | Status e ordenação por vencimento | ⬜ |
| 5 | `alerts` — regras, job Celery, inbox | ⬜ |
| 6 | `exports` — CSV seguro | ⬜ |
| 7 | Row-Level Security e endurecimento | ⬜ |
| 8 | Suite de segurança do MVP | ⬜ |
| 9 | Documentação e seed demo | ⬜ |

### Endpoints disponíveis

| Método | Rota | O que faz |
|---|---|---|
| `GET` | `/api/health/` | Health check com checagem real de banco |
| `POST` | `/api/auth/register/` | Cadastro (RF01) |
| `POST` | `/api/auth/login/` | Login — access no corpo, refresh em cookie httpOnly (RF02) |
| `POST` | `/api/auth/refresh/` | Renova o access, rotaciona o refresh |
| `POST` | `/api/auth/logout/` | Blacklist do refresh + limpa cookie |
| `GET`/`PATCH` | `/api/auth/me/` | Conta autenticada (nome, fuso) |
| `GET`/`POST` | `/api/tables/` | Lista e cria tabelas (RF03, RF04) |
| `GET`/`PATCH`/`DELETE` | `/api/tables/{id}/` | Detalhe com colunas embutidas |
| `GET`/`POST` | `/api/tables/{id}/columns/` | Colunas da tabela (RF05, RF06) |
| `GET`/`PATCH`/`DELETE` | `/api/tables/{id}/columns/{col}/` | Uma coluna |
| `PATCH` | `/api/tables/{id}/columns/reorder/` | Reordena todas as colunas de uma vez |

| `GET`/`POST` | `/api/tables/{id}/records/` | Registros da tabela (RF07) |
| `GET`/`PATCH`/`DELETE` | `/api/tables/{id}/records/{rec}/` | Um registro (RF08, RF09) |

Tipos de coluna: `text`, `number`, `date`, `datetime`, `boolean`, `email`, `select`, `due_date`.

### Como os registros funcionam

Cada registro é **uma linha** com um `data JSONB`, não N linhas de EAV. As chaves do JSONB são os `key` das colunas, e o payload é validado contra a definição da tabela a cada escrita:

```bash
curl -X POST http://localhost:8000/api/tables/$T/records/ \
  -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' \
  -d '{"data": {"cliente":"Empresa A","contrato":"CT-001",
                "data_de_vencimento":"2026-08-20","status":"Ativo"}}'
```

- **Chave desconhecida → 400.** Nada de lixo entrando no JSONB.
- **Tipo errado → 400.** `"true"` não passa por booleano, `20/08/2026` não passa por data, valor fora da lista não passa por `select`.
- **`PATCH` mescla com o estado atual** antes de validar — é o que permite recusar um PATCH que esvazia um campo obrigatório. Olhando só o delta, isso passaria.
- **`due_date` é promovida** de `data[<coluna due_date>]` para uma coluna real no `save()`. É somente leitura na API: mandá-la no corpo não a faz divergir do JSONB.
- **Excluir uma coluna limpa a chave dela** em todos os registros — e zera o `due_date` promovido se era a coluna de vencimento.

Exemplo:

```bash
curl -X POST http://localhost:8000/api/auth/register/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"voce@example.com","name":"Voce","password":"Contrato!Vencendo#2026"}'

curl -c cookies.txt -X POST http://localhost:8000/api/auth/login/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"voce@example.com","password":"Contrato!Vencendo#2026"}'
```

### Decisões de segurança já em vigor

- **Argon2id** como hasher primário; senha validada contra tamanho mínimo, lista de senhas comuns e similaridade com e-mail/nome.
- **Refresh token só em cookie `httpOnly`**, com `path=/api/auth/` — não trafega nas rotas de dados e é invisível para JavaScript. O access (15 min) fica em memória no cliente.
- **Rotação + blacklist** de refresh: cada renovação queima o token anterior, e o logout invalida de fato.
- **E-mail único case-insensitive no banco**, via collation não-determinística — não dá para cadastrar `Ana@x.com` e `ana@x.com` nem inserindo direto no Postgres.
- **django-axes** bloqueia a combinação IP+usuário após 5 falhas (429 por 15 min). Ver a armadilha do `ATOMIC_REQUESTS` em [`docs/data-model.md`](docs/data-model.md#armadilhas-encontradas-na-implementação).
- **Recurso alheio responde 404, nunca 403** — 403 confirmaria que o recurso existe e entregaria informação a quem sonda ids (RS04). Vale também para coleções aninhadas: as colunas de uma tabela que não é sua não existem.
- **O dono vem sempre do token**, nunca do corpo da requisição. Mandar `user` no payload de criação de tabela não muda nada.

### Regras estruturais garantidas pelo banco

Não só pelo serializer — os testes provam cada uma passando por cima da API:

- No máximo **uma coluna `due_date` por tabela** (índice único parcial, RF06).
- **Nome de tabela único por usuário** — dois usuários podem ter tabelas homônimas.
- **`key` de coluna única por tabela**, gerada por slug do rótulo com sufixo em colisão.
- **Posição única por tabela**, com constraint `DEFERRABLE INITIALLY DEFERRED` — é o que permite ao reorder permutar tudo numa transação, passando por estados temporariamente duplicados.
