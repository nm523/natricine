"""Conformance tests for pub/sub implementations.

Usage:
    1. Create a conftest.py with a fixture that provides your implementation:

        import pytest
        from myimpl import MyPubSub

        @pytest.fixture
        async def pubsub():
            async with MyPubSub() as ps:
                yield ps

    2. Create a test file that inherits from the conformance classes:

        from natricine.conformance import PubSubConformance

        class TestMyPubSub(PubSubConformance.Core):
            pass

        class TestMyPubSubFanOut(PubSubConformance.FanOut):
            pass

        # ... etc for each category you want to test

    3. Run pytest as normal. Results show which categories pass/fail.
"""

from collections.abc import AsyncIterator
from typing import Protocol

import anyio
import pytest

from natricine.pubsub import Message, Publisher, Subscriber

EXPECTED_TWO = 2
EXPECTED_THREE = 3
CONCURRENT_COUNT = 5


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
        """Fan-out behavior - multiple subscribers receiving messages."""

        pytestmark = pytest.mark.anyio

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
