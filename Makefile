.PHONY: test lint check sync

sync:
	uv sync

test:
	uv run pytest

lint:
	uv run ruff check packages/

check: lint test
