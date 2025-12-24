"""Integration tests for PostgreSQL pub/sub.

Requires testcontainers and asyncpg:
    pip install natricine-sql[test-postgres]

Or set POSTGRES_URL environment variable to use external PostgreSQL.
"""

import os
import uuid

import anyio
import pytest

try:
    import asyncpg
    from testcontainers.postgres import PostgresContainer

    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False

from natricine_sql import PostgresDialect, SQLConfig, SQLPublisher, SQLSubscriber

from natricine.conformance import PubSubConformance
from natricine.pubsub import Message

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(not HAS_POSTGRES, reason="asyncpg not installed"),
]


class PostgresPubSubAdapter:
    """Adapter for PostgreSQL conformance testing."""

    def __init__(self, pool, dialect, config):
        self._pool = pool
        self._dialect = dialect
        self._config = config
        self._publisher = SQLPublisher(pool, dialect, config)
        self._subscriber = SQLSubscriber(pool, dialect, config)

    async def publish(self, topic: str, *messages):
        await self._publisher.publish(topic, *messages)

    def subscribe(self, topic: str):
        return self._subscriber.subscribe(topic)

    async def close(self):
        await self._publisher.close()
        await self._subscriber.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


@pytest.fixture(scope="session")
def postgres_container():
    """Start a PostgreSQL container for the test session."""
    if os.environ.get("POSTGRES_URL"):
        yield None
        return

    if not HAS_POSTGRES:
        pytest.skip("asyncpg/testcontainers not installed")

    os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

    with PostgresContainer("postgres:16-alpine") as container:
        yield container


@pytest.fixture
async def postgres_pool(postgres_container):
    """Create a PostgreSQL connection pool."""
    if postgres_container is None:
        url = os.environ["POSTGRES_URL"]
    else:
        url = postgres_container.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql://"
        )

    pool = await asyncpg.create_pool(url)
    try:
        yield pool
    finally:
        await pool.close()


@pytest.fixture
async def pubsub(postgres_pool):
    """Provide PostgreSQL pub/sub adapter for conformance testing."""
    dialect = PostgresDialect()
    config = SQLConfig(
        consumer_group=f"test-{uuid.uuid4()}",
        poll_interval=0.05,
        ack_deadline=5.0,
        batch_size=10,
        table_prefix=f"test_{uuid.uuid4().hex[:8]}_",  # Unique prefix per test
    )

    async with PostgresPubSubAdapter(postgres_pool, dialect, config) as ps:
        yield ps


# Basic tests without conformance (for faster feedback)
class TestPostgresBasic:
    """Basic PostgreSQL tests."""

    async def test_publish_and_receive(self, postgres_pool) -> None:
        """Test basic publish and subscribe."""
        dialect = PostgresDialect()
        config = SQLConfig(
            consumer_group="test",
            poll_interval=0.05,
            table_prefix=f"test_{uuid.uuid4().hex[:8]}_",
        )

        pub = SQLPublisher(postgres_pool, dialect, config)
        sub = SQLSubscriber(postgres_pool, dialect, config)

        async with pub, sub:
            await pub.publish("orders", Message(payload=b"test"))

            with anyio.fail_after(2):
                async for msg in sub.subscribe("orders"):
                    assert msg.payload == b"test"
                    await msg.ack()
                    break


# Conformance tests
class TestPostgresCore(PubSubConformance.Core):
    """Core conformance tests for PostgreSQL."""

    pass


class TestPostgresFanOut(PubSubConformance.FanOut):
    """Fan-out tests - skipped for competing consumers."""

    @pytest.mark.skip(reason="SQL uses competing consumers, not broadcast")
    async def test_multiple_subscribers_receive_message(self, pubsub) -> None:
        pass

    @pytest.mark.skip(reason="SQL uses competing consumers, not broadcast")
    async def test_subscriber_gets_own_message_copy(self, pubsub) -> None:
        pass


class TestPostgresAcknowledgment(PubSubConformance.Acknowledgment):
    """Acknowledgment conformance tests for PostgreSQL."""

    pass


class TestPostgresLifecycle(PubSubConformance.Lifecycle):
    """Lifecycle conformance tests for PostgreSQL."""

    pass


class TestPostgresRobustness(PubSubConformance.Robustness):
    """Robustness conformance tests for PostgreSQL."""

    pass
