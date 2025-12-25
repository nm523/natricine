"""Conformance tests for Kafka pub/sub."""

import pytest
from natricine_conformance import PubSubConformance

pytestmark = [pytest.mark.anyio, pytest.mark.containers]


class TestKafkaCore(PubSubConformance.Core):
    """Core pub/sub functionality tests."""

    pass


class TestKafkaAcknowledgment(PubSubConformance.Acknowledgment):
    """Message acknowledgment tests."""

    pass


class TestKafkaLifecycle(PubSubConformance.Lifecycle):
    """Lifecycle management tests."""

    pass


class TestKafkaRobustness(PubSubConformance.Robustness):
    """Robustness tests."""

    pass


class TestKafkaRedelivery(PubSubConformance.Redelivery):
    """Redelivery tests (will run since redelivery_on_nack=True)."""

    pass


class TestKafkaOrdering(PubSubConformance.Ordering):
    """Ordering tests (will run since guaranteed_order=True)."""

    pass


class TestKafkaConcurrentClose(PubSubConformance.ConcurrentClose):
    """Concurrent close tests."""

    pass
