"""Conformance tests for SQL pub/sub using SQLite."""

import uuid

import aiosqlite
import pytest

from natricine.conformance import PubSubConformance
from natricine.backends.sql import SQLConfig, SQLiteDialect, SQLPublisher, SQLSubscriber

pytestmark = pytest.mark.anyio


class SQLPubSubAdapter:
    """Adapter that combines SQLPublisher and SQLSubscriber.

    Provides a unified interface for conformance testing.
    """

    def __init__(self, connection, dialect, config):
        self._connection = connection
        self._dialect = dialect
        self._config = config
        self._publisher = SQLPublisher(connection, dialect, config)
        self._subscriber = SQLSubscriber(connection, dialect, config)

    async def publish(self, topic: str, *messages):
        """Publish messages to a topic."""
        await self._publisher.publish(topic, *messages)

    def subscribe(self, topic: str):
        """Subscribe to a topic."""
        return self._subscriber.subscribe(topic)

    async def close(self):
        """Clean up resources."""
        await self._publisher.close()
        await self._subscriber.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


@pytest.fixture
async def pubsub():
    """Provide SQL pub/sub adapter for conformance testing."""
    # Use in-memory SQLite - fresh database for each test
    connection = await aiosqlite.connect(":memory:")

    dialect = SQLiteDialect()
    config = SQLConfig(
        consumer_group=f"test-{uuid.uuid4()}",
        poll_interval=0.05,  # Fast polling for tests
        ack_deadline=5.0,
        batch_size=10,
    )

    async with SQLPubSubAdapter(connection, dialect, config) as ps:
        yield ps

    await connection.close()


class TestSQLiteCore(PubSubConformance.Core):
    """Core conformance tests for SQLite pub/sub."""

    pass


class TestSQLiteFanOut(PubSubConformance.FanOut):
    """Fan-out conformance tests for SQLite pub/sub.

    Note: SQL pub/sub uses competing consumers pattern (like SQS/Redis consumer groups).
    Each message goes to ONE consumer, not all consumers.
    """

    # SQL competing consumers distribute messages, not broadcast
    @pytest.mark.skip(reason="SQL uses competing consumers, not broadcast")
    async def test_multiple_subscribers_receive_message(self, pubsub) -> None:
        pass

    @pytest.mark.skip(reason="SQL uses competing consumers, not broadcast")
    async def test_subscriber_gets_own_message_copy(self, pubsub) -> None:
        pass


class TestSQLiteAcknowledgment(PubSubConformance.Acknowledgment):
    """Acknowledgment conformance tests for SQLite pub/sub."""

    pass


class TestSQLiteLifecycle(PubSubConformance.Lifecycle):
    """Lifecycle conformance tests for SQLite pub/sub."""

    pass


class TestSQLiteRobustness(PubSubConformance.Robustness):
    """Robustness conformance tests for SQLite pub/sub."""

    pass
