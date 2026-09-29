VERSION := $(shell grep '^version' pyproject.toml | head -1 | cut -d '"' -f 2)

.PHONY: help setup data features split train evaluate package reproduce lint test test-data check api docker-build docker-run simulate monitor tf-validate clean

help: ## List targets with a one-line description
	@grep -E '^[a-zA-Z0-9_-]+:.*##' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*## "}; {printf "  %-16s %s\n", $$1, $$2}'

setup: ## Install dependencies from uv.lock (uv sync --frozen)
	uv sync --frozen

data: ## Run ingest, parse, quality, and tables
	uv run python -m icu.ingest
	uv run python -m icu.parse
	uv run python -m icu.quality
	uv run python -m icu.tables

features: ## Build feature table (python -m icu.features)
	uv run python -m icu.features

split: ## Write stratified train, val, and test ID files
	uv run python -m icu.split

train: ## Tune models on validation and choose threshold
	uv run python -m icu.train

evaluate: ## Score test set and write reports
	@echo "not implemented yet: F7"
	@exit 1

package: ## Write models/<version>/ pipeline and metadata
	@echo "not implemented yet: F8"
	@exit 1

reproduce: ## Full pipeline and compare to committed splits and metrics
	@echo "not implemented yet: F8"
	@exit 1

lint: ## Run ruff check and format check
	uv run ruff check .
	uv run ruff format --check .

test: ## Run pytest excluding tests marked data
	uv run pytest -m "not data"

test-data: ## Run pytest tests that need the real dataset
	uv run pytest -m data

check: ## Lint then run fast tests
	$(MAKE) lint
	$(MAKE) test

api: ## Run FastAPI locally with uvicorn reload
	@echo "not implemented yet: F9"
	@exit 1

docker-build: ## Build API Docker image tagged corvita-icu-api:$(VERSION)
	@echo "not implemented yet: F9"
	@exit 1

docker-run: ## Build image and run on port 8080 with logs/ mounted
	@echo "not implemented yet: F9"
	@exit 1

simulate: ## Replay example requests against a running API
	@echo "not implemented yet: F9"
	@exit 1

monitor: ## Run monitoring check on logs/requests.jsonl
	@echo "not implemented yet: F10"
	@exit 1

tf-validate: ## Terraform fmt check, init without backend, validate
	@echo "not implemented yet: F12"
	@exit 1

clean: ## Remove interim and processed data and Python caches
	rm -rf data/interim data/processed
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
