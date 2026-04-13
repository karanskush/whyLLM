# ============================================================
# LLMDawg Makefile
# All commands are run from the llmdawg/ monorepo root.
# ============================================================

.PHONY: up down logs migrate shell-api test-api test-sdk build-api build-dashboard \
        lint-api typecheck-dashboard install-dashboard worker-local clean help

COMPOSE      := docker compose -f infra/docker-compose.yml
API_SERVICE  := api
PG_SERVICE   := postgres
REDIS_SERVICE:= redis

# Default target
.DEFAULT_GOAL := help

# ---- Infrastructure -----------------------------------------

up: ## Start PostgreSQL + Redis + API (detached)
	$(COMPOSE) up -d --build
	@echo ""
	@echo "Services started. Waiting for health checks..."
	@sleep 3
	@$(COMPOSE) ps

down: ## Stop and remove containers (keeps volumes)
	$(COMPOSE) down

down-v: ## Stop containers AND delete volumes (destructive — loses all data)
	$(COMPOSE) down -v

logs: ## Tail logs for all services
	$(COMPOSE) logs -f

logs-api: ## Tail API logs only
	$(COMPOSE) logs -f $(API_SERVICE)

logs-db: ## Tail PostgreSQL logs only
	$(COMPOSE) logs -f $(PG_SERVICE)

ps: ## Show running services and health status
	$(COMPOSE) ps

# ---- Database -----------------------------------------------

migrate: ## Run Alembic migrations (upgrade head) inside the API container
	$(COMPOSE) exec $(API_SERVICE) alembic upgrade head

migrate-down: ## Roll back one migration step
	$(COMPOSE) exec $(API_SERVICE) alembic downgrade -1

migrate-history: ## Show migration history
	$(COMPOSE) exec $(API_SERVICE) alembic history --verbose

makemigration: ## Generate a new migration (usage: make makemigration MSG="add spans table")
	$(COMPOSE) exec $(API_SERVICE) alembic revision --autogenerate -m "$(MSG)"

db-shell: ## Open a psql shell in the postgres container
	$(COMPOSE) exec $(PG_SERVICE) psql -U llmdawg -d llmdawg

# ---- Development shells -------------------------------------

shell-api: ## exec into the API container (bash)
	$(COMPOSE) exec $(API_SERVICE) bash

shell-redis: ## Open redis-cli in the redis container
	$(COMPOSE) exec $(REDIS_SERVICE) redis-cli

# ---- Testing ------------------------------------------------

test-api: ## Run the full pytest suite inside the API container
	$(COMPOSE) exec $(API_SERVICE) pytest -v --tb=short

test-api-cov: ## Run tests with coverage report
	$(COMPOSE) exec $(API_SERVICE) pytest --cov=llmdawg_api --cov-report=term-missing

# Run tests locally without Docker (requires venv activated)
test-api-local: ## Run pytest locally (requires venv)
	cd apps/api && pytest -v --tb=short

worker-local: ## Start background worker locally (outside Docker, requires venv)
	cd apps/api && python -m llmdawg_api.worker

# ---- Linting & Type Checking --------------------------------

lint-api: ## Run ruff linter on the API source
	$(COMPOSE) exec $(API_SERVICE) ruff check src/

lint-fix: ## Run ruff with auto-fix on the API source
	$(COMPOSE) exec $(API_SERVICE) ruff check src/ --fix

typecheck-api: ## Run mypy on the API source
	$(COMPOSE) exec $(API_SERVICE) mypy src/llmdawg_api

typecheck-dashboard: ## Run tsc type checking on the dashboard
	cd apps/dashboard && npx tsc --noEmit

# ---- Build --------------------------------------------------

build-api: ## Build the API Docker image
	docker build -t llmdawg-api:local apps/api

build-dashboard: ## Build the dashboard Docker image
	docker build -t llmdawg-dashboard:local apps/dashboard

# ---- Local Setup --------------------------------------------

install-dashboard: ## npm install for the dashboard
	cd apps/dashboard && npm install

install-js-sdk: ## npm install for the JS SDK
	cd packages/js-sdk && npm install

setup: ## First-time setup: copy .env.example → .env, install deps
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env from .env.example. Edit it before running make up."; \
	else \
		echo ".env already exists — skipping copy."; \
	fi

# ---- Cleanup ------------------------------------------------

clean: ## Remove Python bytecode, __pycache__, .next build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find apps/dashboard -type d -name ".next" -exec rm -rf {} + 2>/dev/null || true

# ---- Help ---------------------------------------------------

help: ## Show this help message
	@echo ""
	@echo "LLMDawg — available make targets:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*##"}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'
	@echo ""
