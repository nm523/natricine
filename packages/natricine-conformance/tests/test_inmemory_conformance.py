"""Conformance tests for InMemoryPubSub."""

import pytest
from natricine_conformance import PubSubConformance, PubSubFeatures

from natricine.pubsub import InMemoryPubSub


@pytest.fixture
async def pubsub():
    """Provide InMemoryPubSub for conformance testing."""
    async with InMemoryPubSub() as ps:
        yield ps


@pytest.fixture
def features():
    """Declare InMemoryPubSub capabilities."""
    return PubSubFeatures(
        broadcast=True,  # Multiple subscribers get same message
        persistent=False,  # Messages lost on close
        redelivery_on_nack=False,  # Nack doesn't redeliver (no queue)
        guaranteed_order=True,  # Single queue, FIFO
        exactly_once=True,  # No duplicates in memory
    )


class TestInMemoryCore(PubSubConformance.Core):
    """Core conformance tests for InMemoryPubSub."""

    pass


class TestInMemoryFanOut(PubSubConformance.FanOut):
    """Fan-out conformance tests for InMemoryPubSub."""

    pass


class TestInMemoryAcknowledgment(PubSubConformance.Acknowledgment):
    """Acknowledgment conformance tests for InMemoryPubSub."""

    pass


class TestInMemoryLifecycle(PubSubConformance.Lifecycle):
    """Lifecycle conformance tests for InMemoryPubSub."""

    pass


class TestInMemoryRobustness(PubSubConformance.Robustness):
    """Robustness conformance tests for InMemoryPubSub."""

    pass


class TestInMemoryConcurrentClose(PubSubConformance.ConcurrentClose):
    """Concurrent close conformance tests for InMemoryPubSub."""

    pass


class TestInMemoryOrdering(PubSubConformance.Ordering):
    """Ordering conformance tests for InMemoryPubSub."""

    pass


# Redelivery tests skipped - InMemoryPubSub doesn't support redelivery
# Persistence tests skipped - InMemoryPubSub is not persistent
