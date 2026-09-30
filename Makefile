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
	uv run python -m icu.evaluate

package: ## Write models/<version>/ pipeline and metadata
	uv run python -m icu.artifacts

reproduce: ## Full pipeline and compare to committed splits and metrics
	@echo ""
	@echo "=== Reproduction: saving baseline (splits + metrics.json) ==="
	uv run python -m icu.artifacts --save-baseline*
	@echo ""
	@echo "=== Reproduction: running data -> features -> split -> train -> evaluate -> package ==="
	$(MAKE) data features split train evaluate package
	@echo ""
	@echo "=== Reproduction: comparing to baseline ==="
	uv run python -m icu.artifacts --compare-reproduction
	@echo ""

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
	uv run uvicorn icu.api.app:app --reload --host 0.0.0.0 --port 8080

docker-build: ## Build API Docker image tagged corvita-icu-api:$(VERSION)
	docker build -t corvita-icu-api:$(VERSION) .

docker-run: ## Build image and run on port 8080 with logs/ mounted
	@mkdir -p logs
	docker build -t corvita-icu-api:$(VERSION) .
	docker run --rm -p 8080:8080 \
		-e REQUEST_LOG_PATH=/app/logs/requests.jsonl \
		-v "$(CURDIR)/logs:/app/logs" corvita-icu-api:$(VERSION)

simulate: ## Replay test-set requests against a running API
	uv run python scripts/send_requests.py --n 100

monitor: ## Run monitoring check on logs/requests.jsonl
	@mkdir -p logs
	uv run python -m icu.monitor

tf-validate: ## Terraform fmt check, init without backend, validate
	terraform -chdir=infra fmt -check -recursive
	terraform -chdir=infra init -backend=false
	terraform -chdir=infra validate

clean: ## Remove interim and processed data and Python caches
	rm -rf data/interim data/processed
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
