"""Conformance tests for pub/sub implementations.

Usage:
    1. Create a conftest.py with fixtures:

        import pytest
        from myimpl import MyPubSub
        from natricine_conformance import PubSubFeatures

        @pytest.fixture
        async def pubsub():
            async with MyPubSub() as ps:
                yield ps

        @pytest.fixture
        def features():
            return PubSubFeatures(
                broadcast=True,  # Multiple subscribers get same message
                persistent=False,  # Messages lost on close
                redelivery_on_nack=False,  # Nack doesn't redeliver
            )

    2. Create a test file that inherits from the conformance classes:

        from natricine_conformance import PubSubConformance

        class TestMyPubSub(PubSubConformance.Core):
            pass

        class TestMyPubSubFanOut(PubSubConformance.FanOut):
            pass

        # ... etc for each category you want to test

    3. Run pytest as normal. Results show which categories pass/fail.
       Tests auto-skip based on declared features.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

import anyio
import pytest

from natricine.pubsub import Message, Publisher, Subscriber

EXPECTED_TWO = 2
EXPECTED_THREE = 3
CONCURRENT_COUNT = 5
REDELIVERY_COUNT = 3


@dataclass
class PubSubFeatures:
    """Declares capabilities of a PubSub implementation.

    Used by conformance tests to skip tests that don't apply.

    Attributes:
        broadcast: Multiple subscribers each receive every message.
            True for in-memory pub/sub, False for competing consumers
            (SQS, Redis consumer groups).
        persistent: Messages survive subscriber disconnect and reconnect.
            True for durable backends (Kafka, Redis, SQL), False for in-memory.
        redelivery_on_nack: Nack causes message to be redelivered.
            True for most real backends, may be False for simple implementations.
        guaranteed_order: Messages delivered in publish order.
            True for single-partition Kafka, FIFO SQS, False for standard SQS.
        exactly_once: Each message delivered exactly once (no duplicates).
            True for exactly-once systems, False for at-least-once.
    """

    broadcast: bool = True
    persistent: bool = False
    redelivery_on_nack: bool = False
    guaranteed_order: bool = False
    exactly_once: bool = False

    # Timeouts for slow backends (e.g., SQS visibility timeout)
    redelivery_timeout_s: float = 5.0


class PubSub(Publisher, Subscriber, Protocol):
    """Combined protocol for implementations that are both publisher and subscriber."""

    pass


class PubSubConformance:
    """Conformance test suite for pub/sub implementations.

    Organized into categories for clear reporting:
    - Core: Basic publish/subscribe functionality
    - FanOut: Multiple subscriber behavior
    - Acknowledgment: Message ack/nack behavior
    - Lifecycle: Context manager and close behavior
    - Robustness: Concurrent operations and edge cases
    """

    class Core:
        """Core pub/sub functionality - all implementations must pass these."""

        pytestmark = pytest.mark.anyio

        async def test_publish_single_message(self, pubsub: PubSub) -> None:
            """Publishing a single message succeeds."""
            topic = "conformance.core.single"
            msg = Message(payload=b"hello")
            await pubsub.publish(topic, msg)

        async def test_publish_multiple_messages(self, pubsub: PubSub) -> None:
            """Publishing multiple messages in one call succeeds."""
            topic = "conformance.core.multiple"
            await pubsub.publish(
                topic,
                Message(payload=b"one"),
                Message(payload=b"two"),
                Message(payload=b"three"),
            )

        async def test_subscribe_receives_message(self, pubsub: PubSub) -> None:
            """Subscriber receives published messages."""
            topic = "conformance.core.receive"
            sent = Message(payload=b"test message")

            received: list[Message] = []

            async def subscriber() -> None:
                async for msg in pubsub.subscribe(topic):
                    received.append(msg)
                    await msg.ack()
                    break

            async def publisher() -> None:
                await anyio.sleep(0.01)
                await pubsub.publish(topic, sent)

            with anyio.fail_after(2):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(subscriber)
                    tg.start_soon(publisher)

            assert len(received) == 1

        async def test_message_payload_preserved(self, pubsub: PubSub) -> None:
            """Message payload is preserved through publish/subscribe."""
            topic = "conformance.core.payload"
            payload = b"binary\x00payload\xff"
            sent = Message(payload=payload)

            received: list[Message] = []

            async def subscriber() -> None:
                async for msg in pubsub.subscribe(topic):
                    received.append(msg)
                    await msg.ack()
                    break

            async def publisher() -> None:
                await anyio.sleep(0.01)
                await pubsub.publish(topic, sent)

            with anyio.fail_after(2):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(subscriber)
                    tg.start_soon(publisher)

            assert received[0].payload == payload

        async def test_message_metadata_preserved(self, pubsub: PubSub) -> None:
            """Message metadata is preserved through publish/subscribe."""
            topic = "conformance.core.metadata"
            metadata = {"key1": "value1", "key2": "value2"}
            sent = Message(payload=b"test", metadata=metadata)

            received: list[Message] = []

            async def subscriber() -> None:
                async for msg in pubsub.subscribe(topic):
                    received.append(msg)
                    await msg.ack()
                    break

            async def publisher() -> None:
                await anyio.sleep(0.01)
                await pubsub.publish(topic, sent)

            with anyio.fail_after(2):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(subscriber)
                    tg.start_soon(publisher)

            assert received[0].metadata == metadata

        async def test_message_uuid_preserved(self, pubsub: PubSub) -> None:
            """Message UUID is preserved through publish/subscribe."""
            topic = "conformance.core.uuid"
            sent = Message(payload=b"test")

            received: list[Message] = []

            async def subscriber() -> None:
                async for msg in pubsub.subscribe(topic):
                    received.append(msg)
                    await msg.ack()
                    break

            async def publisher() -> None:
                await anyio.sleep(0.01)
                await pubsub.publish(topic, sent)

            with anyio.fail_after(2):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(subscriber)
                    tg.start_soon(publisher)

            assert received[0].uuid == sent.uuid

    class FanOut:
        """Fan-out behavior - multiple subscribers receiving messages.

        Requires: features.broadcast = True
        """

        pytestmark = pytest.mark.anyio

        @pytest.fixture(autouse=True)
        def _require_broadcast(self, features: PubSubFeatures) -> None:
            if not features.broadcast:
                pytest.skip("requires broadcast=True")

        async def test_multiple_subscribers_receive_message(
            self, pubsub: PubSub
        ) -> None:
            """Multiple subscribers each receive the published message."""
            topic = "conformance.fanout.multi"
            sent = Message(payload=b"broadcast")

            received1: list[Message] = []
            received2: list[Message] = []

            async def subscriber1() -> None:
                async for msg in pubsub.subscribe(topic):
                    received1.append(msg)
                    await msg.ack()
                    break

            async def subscriber2() -> None:
                async for msg in pubsub.subscribe(topic):
                    received2.append(msg)
                    await msg.ack()
                    break

            async def publisher() -> None:
                await anyio.sleep(0.02)
                await pubsub.publish(topic, sent)

            with anyio.fail_after(2):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(subscriber1)
                    tg.start_soon(subscriber2)
                    tg.start_soon(publisher)

            assert len(received1) == 1
            assert len(received2) == 1
            assert received1[0].payload == sent.payload
            assert received2[0].payload == sent.payload

        async def test_subscriber_gets_own_message_copy(self, pubsub: PubSub) -> None:
            """Each subscriber gets independent message copies."""
            topic = "conformance.fanout.independent"
            sent = Message(payload=b"independent")

            received1: list[Message] = []
            received2: list[Message] = []

            async def subscriber1() -> None:
                async for msg in pubsub.subscribe(topic):
                    received1.append(msg)
                    await msg.ack()
                    break

            async def subscriber2() -> None:
                async for msg in pubsub.subscribe(topic):
                    received2.append(msg)
                    await msg.ack()
                    break

            async def publisher() -> None:
                await anyio.sleep(0.02)
                await pubsub.publish(topic, sent)

            with anyio.fail_after(2):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(subscriber1)
                    tg.start_soon(subscriber2)
                    tg.start_soon(publisher)

            # Both should be able to ack independently
            assert received1[0]._acked
            assert received2[0]._acked

    class Acknowledgment:
        """Message acknowledgment behavior."""

        pytestmark = pytest.mark.anyio

        async def test_ack_succeeds(self, pubsub: PubSub) -> None:
            """Acknowledging a message succeeds."""
            topic = "conformance.ack.success"
            sent = Message(payload=b"ack me")

            async def subscriber() -> None:
                async for msg in pubsub.subscribe(topic):
                    await msg.ack()
                    assert msg._acked
                    break

            async def publisher() -> None:
                await anyio.sleep(0.01)
                await pubsub.publish(topic, sent)

            with anyio.fail_after(2):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(subscriber)
                    tg.start_soon(publisher)

        async def test_nack_succeeds(self, pubsub: PubSub) -> None:
            """Negative acknowledgment succeeds."""
            topic = "conformance.ack.nack"
            sent = Message(payload=b"nack me")

            async def subscriber() -> None:
                async for msg in pubsub.subscribe(topic):
                    await msg.nack()
                    assert msg._nacked
                    break

            async def publisher() -> None:
                await anyio.sleep(0.01)
                await pubsub.publish(topic, sent)

            with anyio.fail_after(2):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(subscriber)
                    tg.start_soon(publisher)

        async def test_double_ack_raises(self, pubsub: PubSub) -> None:
            """Double-acking a message raises an error."""
            topic = "conformance.ack.double"
            sent = Message(payload=b"double ack")

            received: list[Message] = []

            async def subscriber() -> None:
                async for msg in pubsub.subscribe(topic):
                    received.append(msg)
                    await msg.ack()
                    break

            async def publisher() -> None:
                await anyio.sleep(0.01)
                await pubsub.publish(topic, sent)

            with anyio.fail_after(2):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(subscriber)
                    tg.start_soon(publisher)

            # Double ack should raise
            assert len(received) == 1
            with pytest.raises((ValueError, RuntimeError)):
                await received[0].ack()

    class Lifecycle:
        """Context manager and lifecycle behavior."""

        pytestmark = pytest.mark.anyio

        async def test_context_manager_protocol(self, pubsub: PubSub) -> None:
            """Implementation supports async context manager protocol."""
            # Fixture uses context manager, but verify the protocol exists
            assert hasattr(pubsub, "__aenter__")
            assert hasattr(pubsub, "__aexit__")

        async def test_subscribe_returns_async_iterator(self, pubsub: PubSub) -> None:
            """Subscribe returns an async iterator."""
            topic = "conformance.lifecycle.iterator"
            result = pubsub.subscribe(topic)
            assert isinstance(result, AsyncIterator)

    class Robustness:
        """Robustness under concurrent and edge-case scenarios."""

        pytestmark = pytest.mark.anyio

        async def test_concurrent_publishers(self, pubsub: PubSub) -> None:
            """Multiple concurrent publishers succeed."""
            topic = "conformance.robust.concurrent_pub"
            received: list[Message] = []
            received_count = 0

            async def subscriber() -> None:
                nonlocal received_count
                async for msg in pubsub.subscribe(topic):
                    received.append(msg)
                    await msg.ack()
                    received_count += 1
                    if received_count >= CONCURRENT_COUNT:
                        break

            async def publisher(i: int) -> None:
                await anyio.sleep(0.01)
                await pubsub.publish(topic, Message(payload=f"msg{i}".encode()))

            with anyio.fail_after(2):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(subscriber)
                    for i in range(CONCURRENT_COUNT):
                        tg.start_soon(publisher, i)

            assert len(received) == CONCURRENT_COUNT

        async def test_high_message_volume(self, pubsub: PubSub) -> None:
            """Handles a burst of messages without dropping."""
            topic = "conformance.robust.volume"
            count = 50
            received: list[Message] = []

            async def subscriber() -> None:
                async for msg in pubsub.subscribe(topic):
                    received.append(msg)
                    await msg.ack()
                    if len(received) >= count:
                        break

            async def publisher() -> None:
                await anyio.sleep(0.01)
                for i in range(count):
                    await pubsub.publish(topic, Message(payload=f"msg{i}".encode()))

            with anyio.fail_after(5):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(subscriber)
                    tg.start_soon(publisher)

            assert len(received) == count

    class Redelivery:
        """Redelivery behavior after nack.

        Requires: features.redelivery_on_nack = True
        """

        pytestmark = pytest.mark.anyio

        @pytest.fixture(autouse=True)
        def _require_redelivery(self, features: PubSubFeatures) -> None:
            if not features.redelivery_on_nack:
                pytest.skip("requires redelivery_on_nack=True")

        async def test_nack_triggers_redelivery(
            self, pubsub: PubSub, features: PubSubFeatures
        ) -> None:
            """Nacking a message causes it to be redelivered."""
            topic = "conformance.redelivery.nack"
            sent = Message(payload=b"redeliver me")

            received_uuids: list[str] = []
            nack_count = 0

            async def subscriber() -> None:
                nonlocal nack_count
                async for msg in pubsub.subscribe(topic):
                    received_uuids.append(str(msg.uuid))
                    if nack_count < REDELIVERY_COUNT:
                        nack_count += 1
                        await msg.nack()
                    else:
                        await msg.ack()
                        break

            async def publisher() -> None:
                await anyio.sleep(0.01)
                await pubsub.publish(topic, sent)

            with anyio.fail_after(features.redelivery_timeout_s):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(subscriber)
                    tg.start_soon(publisher)

            # Should have received the same message multiple times
            expected_receives = REDELIVERY_COUNT + 1
            assert len(received_uuids) == expected_receives
            # All receives should be the same message
            assert all(uuid == str(sent.uuid) for uuid in received_uuids)

        async def test_redelivery_preserves_payload(
            self, pubsub: PubSub, features: PubSubFeatures
        ) -> None:
            """Redelivered messages have the same payload."""
            topic = "conformance.redelivery.payload"
            payload = b"preserve this payload"
            sent = Message(payload=payload)

            payloads: list[bytes] = []
            nacked = False

            async def subscriber() -> None:
                nonlocal nacked
                async for msg in pubsub.subscribe(topic):
                    payloads.append(msg.payload)
                    if not nacked:
                        nacked = True
                        await msg.nack()
                    else:
                        await msg.ack()
                        break

            async def publisher() -> None:
                await anyio.sleep(0.01)
                await pubsub.publish(topic, sent)

            with anyio.fail_after(features.redelivery_timeout_s):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(subscriber)
                    tg.start_soon(publisher)

            assert len(payloads) == EXPECTED_TWO
            assert payloads[0] == payload
            assert payloads[1] == payload

    class Persistence:
        """Persistence behavior - messages survive subscriber disconnect.

        Requires: features.persistent = True
        """

        pytestmark = pytest.mark.anyio

        @pytest.fixture(autouse=True)
        def _require_persistence(self, features: PubSubFeatures) -> None:
            if not features.persistent:
                pytest.skip("requires persistent=True")

        async def test_messages_survive_subscriber_close(
            self, pubsub: PubSub
        ) -> None:
            """Messages published while no subscriber exist are not lost.

            Note: This test requires a pubsub_factory fixture that creates
            new instances, since we need to close and recreate subscribers.
            If not available, this test will be skipped.
            """
            # This test requires the ability to create new subscribers
            # which the current fixture model doesn't support well.
            # Skip for now - backends should implement this in their own tests.
            pytest.skip("requires pubsub_factory fixture (not yet implemented)")

    class ConcurrentClose:
        """Safe behavior when closing under concurrent load."""

        pytestmark = pytest.mark.anyio

        async def test_close_during_publish_no_deadlock(
            self, pubsub: PubSub
        ) -> None:
            """Closing while publishing doesn't deadlock."""
            topic = "conformance.concurrent.close_publish"
            closed = False

            async def publisher() -> None:
                nonlocal closed
                for i in range(100):
                    if closed:
                        break
                    try:
                        await pubsub.publish(
                            topic, Message(payload=f"msg{i}".encode())
                        )
                    except Exception:
                        # Expected - pubsub may be closed
                        break
                    await anyio.sleep(0.001)

            async def closer() -> None:
                nonlocal closed
                await anyio.sleep(0.05)
                await pubsub.close()
                closed = True

            # Should complete without deadlock
            with anyio.fail_after(2):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(publisher)
                    tg.start_soon(closer)

        async def test_close_during_subscribe_no_deadlock(
            self, pubsub: PubSub
        ) -> None:
            """Closing while subscribing doesn't deadlock."""
            topic = "conformance.concurrent.close_subscribe"

            async def subscriber() -> None:
                try:
                    async for msg in pubsub.subscribe(topic):
                        await msg.ack()
                except Exception:
                    # Expected - pubsub may be closed
                    pass

            async def closer() -> None:
                await anyio.sleep(0.05)
                await pubsub.close()

            # Should complete without deadlock
            with anyio.fail_after(2):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(subscriber)
                    tg.start_soon(closer)

    class Ordering:
        """Message ordering guarantees.

        Requires: features.guaranteed_order = True
        """

        pytestmark = pytest.mark.anyio

        @pytest.fixture(autouse=True)
        def _require_ordering(self, features: PubSubFeatures) -> None:
            if not features.guaranteed_order:
                pytest.skip("requires guaranteed_order=True")

        async def test_messages_received_in_order(self, pubsub: PubSub) -> None:
            """Messages are received in the order they were published."""
            topic = "conformance.ordering.sequence"
            count = 20
            received_payloads: list[bytes] = []

            async def subscriber() -> None:
                async for msg in pubsub.subscribe(topic):
                    received_payloads.append(msg.payload)
                    await msg.ack()
                    if len(received_payloads) >= count:
                        break

            async def publisher() -> None:
                await anyio.sleep(0.01)
                for i in range(count):
                    await pubsub.publish(
                        topic, Message(payload=f"msg{i:03d}".encode())
                    )

            with anyio.fail_after(5):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(subscriber)
                    tg.start_soon(publisher)

            # Verify order
            expected = [f"msg{i:03d}".encode() for i in range(count)]
            assert received_payloads == expected
