.PHONY: test lint typecheck check sync conformance

sync:
	uv sync

test:
	uv run pytest

lint:
	uv run ruff check packages/

typecheck:
	uv run ty check packages/

check: lint typecheck test

conformance:
	@echo "=== InMemoryPubSub Conformance ==="
	uv run pytest packages/natricine-conformance/tests/test_inmemory_conformance.py -v --tb=short
	@echo ""
	@echo "=== RedisStream Conformance (requires REDIS_URL) ==="
	uv run pytest packages/natricine-conformance/tests/test_redisstream_conformance.py -v --tb=short
