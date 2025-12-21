.PHONY: test lint typecheck check sync

sync:
	uv sync

test:
	uv run pytest

lint:
	uv run ruff check packages/

typecheck:
	uv run ty check packages/

check: lint typecheck test
