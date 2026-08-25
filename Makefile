.PHONY: backup restore restore-ensaio locks locks-check up down build logs sh migrate makemigrations test cov lint lint-fix seed superuser shell reset front-test front-cov front-lint front-sh front-types

up:            ## sobe a stack completa
	docker compose up -d

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f web worker beat

sh:
	docker compose exec web bash

migrate:
	docker compose exec web python manage.py migrate

makemigrations:
	docker compose exec web python manage.py makemigrations

test:
	docker compose exec web pytest -v

cov:            ## suite + gate de cobertura em 85% (.coveragerc)
	docker compose run --rm web pytest --cov

seed:           ## conta demo + tabela Contratos do exemplo da especificação
	docker compose exec web python manage.py seed_demo

lint:           ## regras em ruff.toml — o repo passa limpo
	docker compose run --rm web ruff check .

lint-fix:
	docker compose run --rm web ruff check --fix .

superuser:
	docker compose exec web python manage.py createsuperuser

shell:
	docker compose exec web python manage.py shell

# Apaga o volume do Postgres. Necessário só até a Phase 1 fixar AUTH_USER_MODEL.
reset:
	docker compose down -v && docker compose up -d

# ---------------------------------------------------------------- frontend
#
# Rodam DENTRO do container, como os alvos do backend: `make front-test` não
# exige Node no host. Quem tem Node e quer o ciclo curto usa `npm` direto em
# frontend/ — é a mesma coisa, sem a camada do Docker.

front-test:     ## suíte do frontend (vitest)
	docker compose run --rm frontend npm run test

front-cov:      ## suíte + gate de cobertura em 85% (vitest.config.ts)
	docker compose run --rm frontend npm run test -- --coverage

front-lint:     ## eslint + typecheck, os mesmos passos do CI
	docker compose run --rm frontend npm run lint
	docker compose run --rm frontend npm run typecheck

front-sh:
	docker compose run --rm frontend sh

# Regenera src/api/schema.d.ts a partir do OpenAPI que a API serve. Exige a
# stack no ar (`make up`). O CI roda o mesmo comando e exige diff vazio — se
# este alvo produzir mudança, ela precisa ser commitada.
front-types:    ## regenera os tipos do cliente a partir do schema da API
	docker compose run --rm frontend npm run api:types

locks:          ## regenera requirements/*.lock a partir dos .txt
	@# Dentro do container, e nao na maquina: o lock carrega hashes dos
	@# artefatos resolvidos para ESTE Python e ESTA plataforma. Gerar no
	@# Windows produziria um lock que nao instala na imagem Linux.
	docker compose exec -T web sh -c "\
		pip install --quiet --root-user-action=ignore pip-tools && \
		pip-compile --quiet --generate-hashes --strip-extras \
			--output-file=requirements/base.lock requirements/base.txt && \
		pip-compile --quiet --generate-hashes --strip-extras \
			--constraint=requirements/base.lock \
			--output-file=requirements/dev.lock requirements/dev.txt"
	@echo "locks regenerados — revise o diff antes de commitar"

locks-check:    ## falha se os locks estiverem dessincronizados dos .txt
	@# O mesmo que o CI faz. Recompila para um temporario e compara os PINS —
	@# `nome==versao`, ignorando hashes e comentarios. Duas razoes:
	@#
	@# 1. `--generate-hashes` BAIXA todo artefato resolvido para calcular o
	@#    hash. Sao ~4 minutos e uma dependencia de rede por execucao do
	@#    check, contra ~10 segundos sem. Um check que expira por timeout de
	@#    download reprova PR que nao tem nada de errado.
	@# 2. Aqui a pergunta e "o lock reflete o .txt?", e isso esta nos pins.
	@#    A integridade dos hashes ja e cobrada onde importa: o `pip install
	@#    --require-hashes` do Dockerfile recusa artefato que nao case.
	@#
	@# Sem `diff <(...)`: o shell do container e `dash`, e substituicao de
	@# processo e bashismo — falharia com "Syntax error: redirection
	@# unexpected", que nao tem nada a ver com o lock.
	docker compose exec -T web sh -c "\
		pip install --quiet --root-user-action=ignore pip-tools && \
		pip-compile --quiet --strip-extras \
			--output-file=/tmp/base.check requirements/base.txt && \
		pip-compile --quiet --strip-extras \
			--constraint=requirements/base.lock \
			--output-file=/tmp/dev.check requirements/dev.txt && \
		for n in base dev; do \
			grep -oE '^[A-Za-z0-9_.-]+==[^ ]+' requirements/\$$n.lock | sort > /tmp/\$$n.commitado; \
			grep -oE '^[A-Za-z0-9_.-]+==[^ ]+' /tmp/\$$n.check | sort > /tmp/\$$n.recompilado; \
			diff -u /tmp/\$$n.commitado /tmp/\$$n.recompilado || exit 1; \
		done && \
		echo 'locks em dia'"

backup:         ## dump do Postgres em backups/, com retenção (RETENCAO=7)
	sh docker/backup.sh

restore-ensaio: ## restaura o backup mais recente num Postgres descartável e confere
	@# O alvo que dá sentido ao backup. Não encosta no banco local: sobe um
	@# cluster limpo, restaura, conta o que voltou e destrói o cluster.
	sh docker/restore.sh --ensaio

restore:        ## APAGA o banco local e o restaura de um backup — BACKUP=arquivo
	@test -n "$(BACKUP)" || { \
		echo "uso: CONFIRMA=sim make restore BACKUP=backups/remind-....sql.gz"; \
		echo "     (para só conferir que o backup presta: make restore-ensaio)"; \
		exit 1; \
	}
	sh docker/restore.sh "$(BACKUP)"
