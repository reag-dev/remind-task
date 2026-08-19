.PHONY: up down build logs sh migrate makemigrations test superuser shell reset

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

superuser:
	docker compose exec web python manage.py createsuperuser

shell:
	docker compose exec web python manage.py shell

# Apaga o volume do Postgres. Necessário só até a Phase 1 fixar AUTH_USER_MODEL.
reset:
	docker compose down -v && docker compose up -d
