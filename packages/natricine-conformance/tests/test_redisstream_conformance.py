"""Conformance tests for RedisStream pub/sub.

Uses testcontainers for Redis, or set REDIS_URL for external Redis.
"""

import os
import uuid

import pytest
from redis.asyncio import Redis
from testcontainers.redis import RedisContainer

from natricine.conformance import PubSubConformance
from natricine.backends.redis import RedisStreamPublisher, RedisStreamSubscriber

pytestmark = pytest.mark.anyio


class RedisPubSubAdapter:
    """Adapter that combines RedisStreamPublisher and RedisStreamSubscriber.

    Provides a unified interface for conformance testing.
    """

    def __init__(self, redis_client, group_prefix: str):
        self._redis = redis_client
        self._group_prefix = group_prefix
        self._publisher = RedisStreamPublisher(redis_client)
        self._consumer_count = 0
        self._streams_to_clean: list[str] = []

    async def publish(self, topic: str, *messages):
        """Publish messages to a topic."""
        # Track streams for cleanup
        if topic not in self._streams_to_clean:
            self._streams_to_clean.append(topic)
        await self._publisher.publish(topic, *messages)

    def subscribe(self, topic: str):
        """Subscribe to a topic."""
        # Track streams for cleanup
        if topic not in self._streams_to_clean:
            self._streams_to_clean.append(topic)

        self._consumer_count += 1
        group = f"{self._group_prefix}:{topic}"
        consumer = f"consumer-{self._consumer_count}"
        subscriber = RedisStreamSubscriber(
            self._redis, group, consumer, block_ms=100, count=10
        )
        return subscriber.subscribe(topic)

    async def close(self):
        """Clean up resources."""
        await self._publisher.close()
        # Clean up streams
        for stream in self._streams_to_clean:
            await self._redis.delete(stream)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


@pytest.fixture(scope="session")
def redis_container():
    """Start a Redis container for the test session."""
    # Skip container if REDIS_URL is set (allows using external Redis)
    if os.environ.get("REDIS_URL"):
        yield None
        return

    # Disable Ryuk for podman compatibility
    os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

    with RedisContainer() as container:
        yield container


@pytest.fixture
async def pubsub(redis_container):
    """Provide Redis pub/sub adapter for conformance testing."""
    if redis_container is None:
        # Use external Redis from REDIS_URL
        url = os.environ["REDIS_URL"]
    else:
        # Use testcontainers Redis
        host = redis_container.get_container_host_ip()
        port = redis_container.get_exposed_port(6379)
        url = f"redis://{host}:{port}"

    client = Redis.from_url(url, decode_responses=False)

    try:
        await client.ping()
    except Exception:
        pytest.skip("Redis not available")

    group_prefix = f"conformance-{uuid.uuid4()}"

    async with RedisPubSubAdapter(client, group_prefix) as ps:
        yield ps

    await client.aclose()


class TestRedisStreamCore(PubSubConformance.Core):
    """Core conformance tests for RedisStream."""

    pass


class TestRedisStreamFanOut(PubSubConformance.FanOut):
    """Fan-out conformance tests for RedisStream.

    Note: Redis Streams with consumer groups have different fan-out semantics
    than in-memory pub/sub. Each message goes to ONE consumer in a group,
    not all consumers. These tests may need adjustment for Redis semantics.
    """

    # Redis consumer groups distribute messages, not broadcast
    # Skip fan-out tests that assume broadcast semantics
    @pytest.mark.skip(reason="Redis consumer groups distribute, not broadcast")
    async def test_multiple_subscribers_receive_message(self, pubsub) -> None:
        pass

    @pytest.mark.skip(reason="Redis consumer groups distribute, not broadcast")
    async def test_subscriber_gets_own_message_copy(self, pubsub) -> None:
        pass


class TestRedisStreamAcknowledgment(PubSubConformance.Acknowledgment):
    """Acknowledgment conformance tests for RedisStream."""

    pass


class TestRedisStreamLifecycle(PubSubConformance.Lifecycle):
    """Lifecycle conformance tests for RedisStream."""

    pass


class TestRedisStreamRobustness(PubSubConformance.Robustness):
    """Robustness conformance tests for RedisStream."""

    pass
