"""Test fixtures for natricine-kafka."""

import os
import uuid
from collections.abc import AsyncIterator, Generator

import pytest
from natricine_conformance import PubSubFeatures
from natricine_kafka import (
    ConsumerConfig,
    KafkaPublisher,
    KafkaSubscriber,
    ProducerConfig,
)
from testcontainers.kafka import KafkaContainer

from natricine.pubsub import Message


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def kafka_container() -> Generator[KafkaContainer | None, None, None]:
    """Start a Kafka container for the test session."""
    # Skip container if KAFKA_BOOTSTRAP_SERVERS is set (allows using external Kafka)
    if os.environ.get("KAFKA_BOOTSTRAP_SERVERS"):
        yield None
        return

    # Disable Ryuk for podman compatibility
    os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

    with KafkaContainer() as container:
        yield container


@pytest.fixture
def bootstrap_servers(kafka_container: KafkaContainer | None) -> str:
    """Get the Kafka bootstrap servers address."""
    if kafka_container is None:
        return os.environ["KAFKA_BOOTSTRAP_SERVERS"]
    return kafka_container.get_bootstrap_server()


@pytest.fixture
def features() -> PubSubFeatures:
    """Kafka pub/sub capabilities."""
    return PubSubFeatures(
        broadcast=False,  # Competing consumers in same group
        persistent=True,  # Kafka retains messages
        redelivery_on_nack=True,  # We seek back on nack
        guaranteed_order=True,  # Within single partition
        exactly_once=False,  # At-least-once by default
        redelivery_timeout_s=10.0,  # Give time for redelivery
    )


class KafkaPubSub:
    """Combined publisher/subscriber for conformance tests."""

    def __init__(self, bootstrap_servers: str, group_id: str) -> None:
        producer_config = ProducerConfig(bootstrap_servers=bootstrap_servers)
        consumer_config = ConsumerConfig(
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
        )
        self._publisher = KafkaPublisher(producer_config)
        self._subscriber = KafkaSubscriber(consumer_config)

    async def publish(self, topic: str, *messages: Message) -> None:
        return await self._publisher.publish(topic, *messages)

    def subscribe(self, topic: str) -> AsyncIterator[Message]:
        return self._subscriber.subscribe(topic)

    async def close(self) -> None:
        """Close without blocking - for concurrent close tests."""
        await self._publisher.close()
        await self._subscriber.close()

    async def __aenter__(self) -> "KafkaPubSub":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Proper cleanup on context exit."""
        # Stop publisher's producer if started
        self._publisher._closed = True
        if self._publisher._producer is not None:
            await self._publisher._producer.stop()
            self._publisher._producer = None
        # Subscriber cleanup
        self._subscriber._closed = True


@pytest.fixture
async def pubsub(bootstrap_servers: str) -> AsyncIterator[KafkaPubSub]:
    """Create a Kafka pubsub instance for testing."""
    # Unique group ID per test to avoid interference
    group_id = f"test-{uuid.uuid4()}"
    async with KafkaPubSub(bootstrap_servers, group_id) as ps:
        yield ps
