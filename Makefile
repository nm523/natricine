.DEFAULT_GOAL := all

.PHONY: help
help: ## Show this help
	@echo "Usage: make [target]"
	@echo ""
	@awk '/^[a-zA-Z0-9_-]+:.*?##/ { \
		helpMessage = match($$0, /## (.*)/); \
		if (helpMessage) { \
			target = $$1; \
			sub(/:/, "", target); \
			printf "  \033[36m%-15s\033[0m %s\n", target, substr($$0, RSTART + 3, RLENGTH); \
		} \
	}' $(MAKEFILE_LIST)

.PHONY: sync
sync: ## Sync dependencies
	uv sync

.PHONY: format
format: ## Format code with ruff
	uv run ruff format packages/
	uv run ruff check --fix --fix-only packages/

.PHONY: lint
lint: ## Lint code with ruff
	uv run ruff check packages/

.PHONY: typecheck
typecheck: ## Type check with ty
	uv run ty check packages/

.PHONY: test
test: ## Run tests (use 'make test-all' to include container tests)
	uv run pytest -m "not containers"

.PHONY: test-all
test-all: ## Run all tests including container-based tests
	uv run pytest

.PHONY: test-v
test-v: ## Run tests with verbose output
	uv run pytest -v

.PHONY: check
check: lint typecheck test ## Run lint, typecheck, and tests

.PHONY: all
all: format check ## Format and run all checks

.PHONY: conformance
conformance: ## Run conformance tests (requires Redis/AWS containers)
	@echo "=== InMemoryPubSub Conformance ==="
	uv run pytest packages/natricine-conformance/tests/test_inmemory_conformance.py -v --tb=short
	@echo ""
	@echo "=== RedisStream Conformance ==="
	uv run pytest packages/natricine-conformance/tests/test_redisstream_conformance.py -v --tb=short
	@echo ""
	@echo "=== SQS Conformance ==="
	uv run pytest packages/natricine-aws/tests/test_sqs_conformance.py -v --tb=short

.PHONY: build
build: ## Build all packages
	uv build --all

.PHONY: docs
docs: ## Build documentation
	uv run mkdocs build

.PHONY: docs-serve
docs-serve: ## Serve documentation locally
	uv run mkdocs serve
