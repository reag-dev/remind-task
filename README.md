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

**Phase 0 concluída** — scaffold e infraestrutura local.

| Phase | Escopo | Status |
|---|---|---|
| 0 | Scaffold, Docker Compose, health check | ✅ |
| 1 | `accounts` — usuário customizado, JWT, Argon2, axes | ⬜ |
| 2 | `tables` — tabelas e colunas dinâmicas | ⬜ |
| 3 | `records` — registros JSONB validados | ⬜ |
| 4 | Status e ordenação por vencimento | ⬜ |
| 5 | `alerts` — regras, job Celery, inbox | ⬜ |
| 6 | `exports` — CSV seguro | ⬜ |
| 7 | Row-Level Security e endurecimento | ⬜ |
| 8 | Suite de segurança do MVP | ⬜ |
| 9 | Documentação e seed demo | ⬜ |

> **Atenção antes da Phase 1:** `AUTH_USER_MODEL` ainda não está definido e nenhuma migration foi aplicada. Isso é intencional — trocar o modelo de usuário depois do primeiro `migrate` exige recriar o banco. A Phase 1 define `AUTH_USER_MODEL = "accounts.User"` **antes** de qualquer `migrate`. Se você rodou `migrate` por engano, use `make reset`.
