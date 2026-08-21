.PHONY: up down build logs sh migrate makemigrations test cov lint lint-fix seed superuser shell reset front-test front-cov front-lint front-sh front-types

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
