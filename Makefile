.PHONY: up down build logs sh migrate makemigrations test lint lint-fix superuser shell reset

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
