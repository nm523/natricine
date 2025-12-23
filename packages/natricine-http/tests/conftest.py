"""Test fixtures for natricine-http."""

import pytest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
