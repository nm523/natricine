"""Conformance tests for InMemoryPubSub."""

import pytest
from natricine_conformance import PubSubConformance

from natricine.pubsub import InMemoryPubSub


@pytest.fixture
async def pubsub():
    """Provide InMemoryPubSub for conformance testing."""
    async with InMemoryPubSub() as ps:
        yield ps


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
