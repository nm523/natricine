"""Test fixtures for natricine-sql."""

from collections.abc import AsyncGenerator

import aiosqlite
import pytest
from natricine_sql import SQLConfig, SQLiteDialect, SQLPublisher, SQLSubscriber


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def sqlite_connection():
    """Create an in-memory SQLite connection for testing."""
    conn = await aiosqlite.connect(":memory:")
    try:
        yield conn
    finally:
        await conn.close()


@pytest.fixture
def sqlite_dialect() -> SQLiteDialect:
    """Create a SQLite dialect."""
    return SQLiteDialect()


@pytest.fixture
def sql_config() -> SQLConfig:
    """Create a test configuration with short timeouts."""
    return SQLConfig(
        consumer_group="test",
        poll_interval=0.1,  # Fast polling for tests
        ack_deadline=5.0,
        batch_size=10,
    )


@pytest.fixture
async def sqlite_publisher(
    sqlite_connection, sqlite_dialect, sql_config
) -> AsyncGenerator[SQLPublisher, None]:
    """Create a SQLite publisher for testing."""
    async with SQLPublisher(
        sqlite_connection, sqlite_dialect, sql_config
    ) as publisher:
        yield publisher


@pytest.fixture
async def sqlite_subscriber(
    sqlite_connection, sqlite_dialect, sql_config
) -> AsyncGenerator[SQLSubscriber, None]:
    """Create a SQLite subscriber for testing."""
    async with SQLSubscriber(
        sqlite_connection, sqlite_dialect, sql_config
    ) as subscriber:
        yield subscriber
