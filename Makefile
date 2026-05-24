# Convenience commands. Native dev: Django/Celery run on host Python against
# infra (postgres, redis, rabbitmq, stripe-mock) in Docker. The test suite is
# Bun/TypeScript and lives in tests-ts/; it talks to a running server over HTTP.

.PHONY: up down reset-full migrate makemigrations shell test bootstrap provision-fixtures logs \
        runserver worker beat run-all \
        lint lint-py lint-ts fmt fmt-py fmt-ts check typecheck \
        k6-smoke k6-browse k6-cart k6-checkout k6-idempotency

PY := .venv/Scripts/python.exe

up:
	docker compose -f docker-compose.infra.yml up -d

down:
	docker compose -f docker-compose.infra.yml down

# Destructive full blank-slate: wipes postgres/redis/rabbitmq/minio volumes,
# brings the stack back up, then waits for Postgres + migrates + seeds.
# After this finishes, restart `make run-all` so app/celery reconnect.
reset-full:
	docker compose -f docker-compose.infra.yml down -v
	docker compose -f docker-compose.infra.yml up -d
	powershell -ExecutionPolicy Bypass -File ./reset-full.ps1

migrate:
	$(PY) manage.py migrate

makemigrations:
	$(PY) manage.py makemigrations

shell:
	$(PY) manage.py shell

test:
	bun test --cwd tests-ts

# Minimum-viable DB state: one Django superuser (platform admin).
# Every other piece of state (tenants, gateway configs, customers,
# products) is created via the admin REST API once this user can log in.
bootstrap:
	$(PY) manage.py shell -c "exec(open('scripts/bootstrap.py').read())"

# Provision test fixtures (tenants, customers, products, coupons) via
# the admin REST API. Required before `make test` on a fresh DB.
# Captures dynamic IDs into tests-ts/.fixtures.tson (gitignored).
provision-fixtures:
	cd tests-ts && bun run provision

logs:
	docker compose -f docker-compose.infra.yml logs -f

# --- App processes ------------------------------------------------------------
# Three things run alongside infra: Django dev server, Celery worker, Celery
# beat. `run-all` launches each in its own console window so logs stay
# readable. Celery worker uses `-P solo` because the default prefork pool
# doesn't work on Windows.

runserver:
	$(PY) manage.py runserver


# --- Linting / formatting -----------------------------------------------------
# Python (ruff) + TypeScript (Biome). `fmt` applies fixes; `lint` is read-only.
# `check` is the CI-friendly aggregate (no writes, fails on any issue).

fmt: fmt-py fmt-ts

lint: lint-py lint-ts

check: ## CI-style: no writes, exits non-zero on any finding
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .
	cd tests-ts && bun run check
	cd tests-ts && bun run typecheck

fmt-py:
	$(PY) -m ruff format .
	$(PY) -m ruff check --fix .

lint-py:
	$(PY) -m ruff check .

fmt-ts:
	cd tests-ts && bun run check:fix

lint-ts:
	cd tests-ts && bun run lint

typecheck:
	cd tests-ts && bun run typecheck
	cd tests-ts && bunx tsc --noEmit -p k6/tsconfig.json

# --- k6 stress / load scenarios ----------------------------------------------
# Require k6 on PATH (winget install k6 / brew install k6) and a running server
# with fixtures provisioned (make provision-fixtures). See tests-ts/k6/README.md
# for what each scenario does and how to tune VU counts via env vars.

k6-smoke:
	k6 run tests-ts/k6/scenarios/smoke.ts

k6-browse:
	k6 run tests-ts/k6/scenarios/browse-load.ts

k6-cart:
	k6 run tests-ts/k6/scenarios/cart-contention.ts

k6-checkout:
	k6 run tests-ts/k6/scenarios/checkout-stress.ts

k6-idempotency:
	k6 run tests-ts/k6/scenarios/idempotency-storm.ts
