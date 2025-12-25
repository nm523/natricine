"""Conformance tests for SQS pub/sub.

These tests require Docker/podman with localstack.
"""

import uuid

import pytest

try:
    from natricine_conformance import PubSubConformance, PubSubFeatures

    CONFORMANCE_AVAILABLE = True
except ImportError:
    CONFORMANCE_AVAILABLE = False
    PubSubConformance = None  # type: ignore[misc, assignment]
    PubSubFeatures = None  # type: ignore[misc, assignment]

from natricine_aws import SQSPublisher, SQSSubscriber

# Skip all tests if conformance package not available
pytestmark = [
    pytest.mark.containers,
    pytest.mark.skipif(
        not CONFORMANCE_AVAILABLE,
        reason="natricine-conformance not installed",
    ),
]


class SQSPubSubAdapter:
    """Adapter that combines SQSPublisher and SQSSubscriber.

    Provides a unified interface for conformance testing.
    """

    def __init__(self, session, endpoint_url: str, prefix: str):
        self._session = session
        self._endpoint_url = endpoint_url
        self._prefix = prefix
        self._publisher = SQSPublisher(session, endpoint_url=endpoint_url)
        self._subscriber = SQSSubscriber(session, endpoint_url=endpoint_url)

    def _queue_name(self, topic: str) -> str:
        """Convert topic to valid SQS queue name."""
        sanitized = topic.replace(".", "-")
        return f"{self._prefix}-{sanitized}"

    async def publish(self, topic: str, *messages):
        """Publish messages to a topic (queue)."""
        await self._publisher.publish(self._queue_name(topic), *messages)

    def subscribe(self, topic: str):
        """Subscribe to a topic (queue)."""
        return self._subscriber.subscribe(self._queue_name(topic))

    async def close(self):
        """Clean up resources."""
        await self._publisher.close()
        await self._subscriber.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


@pytest.fixture
async def pubsub(session, endpoint_url):
    """Provide SQS pub/sub adapter for conformance testing."""
    prefix = f"conformance-{uuid.uuid4().hex[:8]}"

    async with SQSPubSubAdapter(session, endpoint_url, prefix) as ps:
        yield ps


@pytest.fixture
def features():
    """Declare SQS capabilities."""
    return PubSubFeatures(
        broadcast=False,  # Competing consumers, not broadcast
        persistent=True,  # Messages survive subscriber disconnect
        redelivery_on_nack=True,  # Visibility timeout triggers redelivery
        guaranteed_order=False,  # Standard SQS doesn't guarantee order
        exactly_once=False,  # At-least-once delivery
        redelivery_timeout_s=35.0,  # SQS visibility timeout is 30s
    )


if CONFORMANCE_AVAILABLE:

    class TestSQSCore(PubSubConformance.Core):
        """Core conformance tests for SQS."""

        pass

    class TestSQSFanOut(PubSubConformance.FanOut):
        """Fan-out conformance tests for SQS.

        Skipped: SQS has competing consumer semantics.
        """

        pass

    class TestSQSAcknowledgment(PubSubConformance.Acknowledgment):
        """Acknowledgment conformance tests for SQS."""

        pass

    class TestSQSLifecycle(PubSubConformance.Lifecycle):
        """Lifecycle conformance tests for SQS."""

        pass

    class TestSQSRobustness(PubSubConformance.Robustness):
        """Robustness conformance tests for SQS."""

        pass

    class TestSQSConcurrentClose(PubSubConformance.ConcurrentClose):
        """Concurrent close conformance tests for SQS."""

        pass

    class TestSQSRedelivery(PubSubConformance.Redelivery):
        """Redelivery conformance tests for SQS."""

        pass
