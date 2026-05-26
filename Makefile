DOCKER_COMPOSE = $(if $(DOCKER_SUDO),sudo docker compose,docker compose)

.PHONY: up down build migrate test lint seed es-setup demo-reset-ingest demo-price-drop crawl-materiel-demo crawl-materiel-ingest crawl-ldlc-demo crawl-ldlc-ingest scheduler-materiel-up scheduler-materiel-down scheduler-materiel-logs scheduler-materiel-status scheduler-ldlc-up scheduler-ldlc-down scheduler-ldlc-logs scheduler-ldlc-status scheduler-up scheduler-down

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

demo-price-drop:
	PRICE_CHANGE_FIXTURE=/app/tests/fixtures/price_drop/ldlc_price_drop.json ./scripts/demo_reset_ingest.sh

crawl-materiel-demo:
	$(DOCKER_COMPOSE) run --rm crawler python -m apps.crawler.scripts.run_spider materiel --itemcount 20 --output /app/apps/crawler/materiel_crawl_demo.json

crawl-materiel-ingest:
	$(DOCKER_COMPOSE) run --rm crawler python -m apps.crawler.scripts.run_spider materiel --itemcount 20 --output /app/apps/crawler/materiel_crawl_ingest.json --ingest

crawl-ldlc-demo:
	$(DOCKER_COMPOSE) run --rm crawler python -m apps.crawler.scripts.run_spider ldlc --itemcount 20 --output /app/apps/crawler/ldlc_crawl_demo.json

crawl-ldlc-ingest:
	$(DOCKER_COMPOSE) run --rm crawler python -m apps.crawler.scripts.run_spider ldlc --itemcount 20 --output /app/apps/crawler/ldlc_crawl_ingest.json --ingest

scheduler-materiel-up:
	@test -f .env || cp .env.example .env
	$(DOCKER_COMPOSE) --profile scheduler up -d crawler-scheduler-materiel

scheduler-materiel-down:
	$(DOCKER_COMPOSE) --profile scheduler stop crawler-scheduler-materiel

scheduler-materiel-logs:
	$(DOCKER_COMPOSE) --profile scheduler logs -f crawler-scheduler-materiel

scheduler-materiel-status:
	$(DOCKER_COMPOSE) --profile scheduler ps crawler-scheduler-materiel

scheduler-ldlc-up:
	@test -f .env || cp .env.example .env
	$(DOCKER_COMPOSE) --profile scheduler up -d crawler-scheduler-ldlc

scheduler-ldlc-down:
	$(DOCKER_COMPOSE) --profile scheduler stop crawler-scheduler-ldlc

scheduler-ldlc-logs:
	$(DOCKER_COMPOSE) --profile scheduler logs -f crawler-scheduler-ldlc

scheduler-ldlc-status:
	$(DOCKER_COMPOSE) --profile scheduler ps crawler-scheduler-ldlc

scheduler-up:
	@test -f .env || cp .env.example .env
	$(DOCKER_COMPOSE) --profile scheduler up -d crawler-scheduler-materiel crawler-scheduler-ldlc

scheduler-down:
	$(DOCKER_COMPOSE) --profile scheduler stop crawler-scheduler-materiel crawler-scheduler-ldlc

logs:
	$(DOCKER_COMPOSE) logs -f

ps:
	$(DOCKER_COMPOSE) ps
