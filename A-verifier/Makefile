.PHONY: up down build migrate test lint seed es-setup demo-reset-ingest

up:
	@test -f .env || cp .env.example .env
	docker compose up -d

down:
	docker compose down

build:
	docker compose build

migrate:
	docker compose exec api alembic upgrade head

test:
	docker compose exec api pytest -q

lint:
	python -m py_compile $$(git ls-files '*.py')
	ruff check .

seed:
	docker compose exec api python -m apps.api.scripts.seed

es-setup:
	docker compose exec api python -m apps.api.scripts.es_setup

demo-reset-ingest:
	./scripts/demo_reset_ingest.sh

logs:
	docker compose logs -f

ps:
	docker compose ps
