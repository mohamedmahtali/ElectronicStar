#!/usr/bin/env bash
set -euo pipefail

compose=(docker compose)
if [[ "${DOCKER_SUDO:-0}" == "1" ]]; then
  compose=(sudo docker compose)
fi

postgres_db="${POSTGRES_DB:-electronic_star}"
postgres_user="${POSTGRES_USER:-app}"
products_index="${PRODUCTS_INDEX:-products-write-v1}"
fixture_set="${DEMO_FIXTURE_SET:-integration}"
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
run_args=(--rm)
fixtures=()

if [[ "$fixture_set" == "live" ]]; then
  fixtures=(
    "${LDLC_FIXTURE:-/app/apps/crawler/ldlc_test.json}"
    "${MATERIEL_FIXTURE:-/app/apps/crawler/materiel_test.json}"
  )
else
  run_args+=(-v "${project_root}/tests:/app/tests:ro")
  fixtures=(
    "${LDLC_FIXTURE:-/app/tests/fixtures/ingest/ldlc.json}"
    "${MATERIEL_FIXTURE:-/app/tests/fixtures/ingest/materiel.json}"
    "${PRICE_CHANGE_FIXTURE:-/app/tests/fixtures/ingest/ldlc_price_change.json}"
  )
fi

echo "Starting services..."
"${compose[@]}" up -d postgres elasticsearch redis api

echo "Applying migrations and seeding merchants..."
"${compose[@]}" exec -T api alembic upgrade head
"${compose[@]}" exec -T api python -m apps.api.scripts.seed

echo "Resetting Postgres business tables..."
"${compose[@]}" exec -T postgres psql -U "$postgres_user" -d "$postgres_db" -c "
truncate table price_history, offers, product_aliases, match_review_queue, products restart identity cascade;
"

echo "Resetting Elasticsearch index..."
"${compose[@]}" exec -T elasticsearch curl -fsS -X DELETE "http://localhost:9200/${products_index}" >/dev/null || true
"${compose[@]}" exec -T api python -m apps.api.scripts.es_setup

echo "Ingesting ${fixture_set} demo fixtures..."
for fixture in "${fixtures[@]}"; do
  "${compose[@]}" run "${run_args[@]}" crawler python -m apps.crawler.scripts.ingest_json "$fixture"
done

echo "Current demo counts:"
"${compose[@]}" exec -T postgres psql -U "$postgres_user" -d "$postgres_db" -c "
select 'merchants' table_name, count(*) from merchants
union all select 'products', count(*) from products
union all select 'offers', count(*) from offers
union all select 'price_history', count(*) from price_history
union all select 'match_review_queue', count(*) from match_review_queue;
"
