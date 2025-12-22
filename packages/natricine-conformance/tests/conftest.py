"""Shared fixtures for conformance tests."""

import pytest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
