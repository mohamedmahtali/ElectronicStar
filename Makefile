DOCKER_COMPOSE = $(if $(DOCKER_SUDO),sudo docker compose,docker compose)

.PHONY: up down build migrate test lint seed es-setup demo-reset-ingest crawl-materiel-demo crawl-materiel-ingest scheduler-materiel-up scheduler-materiel-down scheduler-materiel-logs scheduler-materiel-status

up:
	@test -f .env || cp .env.example .env
	$(DOCKER_COMPOSE) up -d

down:
	$(DOCKER_COMPOSE) down

build:
	$(DOCKER_COMPOSE) build

migrate:
	$(DOCKER_COMPOSE) exec api alembic upgrade head

test:
	$(DOCKER_COMPOSE) exec api pytest -q

lint:
	python -m py_compile $$(git ls-files '*.py')
	ruff check .

seed:
	$(DOCKER_COMPOSE) exec api python -m apps.api.scripts.seed

es-setup:
	$(DOCKER_COMPOSE) exec api python -m apps.api.scripts.es_setup

demo-reset-ingest:
	./scripts/demo_reset_ingest.sh

crawl-materiel-demo:
	$(DOCKER_COMPOSE) run --rm crawler python -m apps.crawler.scripts.run_spider materiel --itemcount 20 --output /app/apps/crawler/materiel_crawl_demo.json

crawl-materiel-ingest:
	$(DOCKER_COMPOSE) run --rm crawler python -m apps.crawler.scripts.run_spider materiel --itemcount 20 --output /app/apps/crawler/materiel_crawl_ingest.json --ingest

scheduler-materiel-up:
	@test -f .env || cp .env.example .env
	$(DOCKER_COMPOSE) --profile scheduler up -d crawler-scheduler-materiel

scheduler-materiel-down:
	$(DOCKER_COMPOSE) --profile scheduler stop crawler-scheduler-materiel

scheduler-materiel-logs:
	$(DOCKER_COMPOSE) --profile scheduler logs -f crawler-scheduler-materiel

scheduler-materiel-status:
	$(DOCKER_COMPOSE) --profile scheduler ps crawler-scheduler-materiel

logs:
	$(DOCKER_COMPOSE) logs -f

ps:
	$(DOCKER_COMPOSE) ps
