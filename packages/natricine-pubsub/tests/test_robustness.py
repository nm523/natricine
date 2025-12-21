"""Robustness tests: deadlocks, backpressure, cancellation."""

import anyio
import pytest

from natricine_pubsub import InMemoryPubSub, Message

pytestmark = pytest.mark.anyio

TIMEOUT_SECONDS = 2
SMALL_BUFFER = 5
MESSAGE_COUNT_EXCEEDS_BUFFER = 10


class TestDeadlocks:
    async def test_slow_subscriber_does_not_block_publisher(self) -> None:
        """Publisher should not deadlock when subscriber is slow."""
        async with InMemoryPubSub(buffer_size=SMALL_BUFFER) as pubsub:
            received: list[Message] = []
            publish_complete = anyio.Event()

            async def slow_subscriber() -> None:
                async for msg in pubsub.subscribe("topic"):
                    await anyio.sleep(0.1)  # Simulate slow processing
                    received.append(msg)
                    if publish_complete.is_set() and len(received) >= SMALL_BUFFER:
                        break

            async def publisher() -> None:
                for i in range(SMALL_BUFFER):
                    await pubsub.publish("topic", Message(payload=f"msg-{i}".encode()))
                publish_complete.set()

            with anyio.fail_after(TIMEOUT_SECONDS):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(slow_subscriber)
                    await anyio.sleep(0.01)  # Let subscriber start
                    tg.start_soon(publisher)

            assert len(received) == SMALL_BUFFER

    async def test_multiple_slow_subscribers_independent(self) -> None:
        """Slow subscriber should not block other subscribers."""
        async with InMemoryPubSub() as pubsub:
            fast_received: list[Message] = []
            slow_received: list[Message] = []
            fast_done = anyio.Event()

            async def fast_subscriber() -> None:
                async for msg in pubsub.subscribe("topic"):
                    fast_received.append(msg)
                    if len(fast_received) >= SMALL_BUFFER:
                        fast_done.set()
                        break

            async def slow_subscriber() -> None:
                async for msg in pubsub.subscribe("topic"):
                    await anyio.sleep(0.5)  # Very slow
                    slow_received.append(msg)
                    break

            async def publisher() -> None:
                await anyio.sleep(0.01)
                for i in range(SMALL_BUFFER):
                    await pubsub.publish("topic", Message(payload=f"msg-{i}".encode()))

            with anyio.fail_after(TIMEOUT_SECONDS):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(fast_subscriber)
                    tg.start_soon(slow_subscriber)
                    tg.start_soon(publisher)
                    await fast_done.wait()
                    tg.cancel_scope.cancel()

            # Fast subscriber got all messages quickly
            assert len(fast_received) == SMALL_BUFFER


class TestBackpressure:
    async def test_buffer_full_blocks_publisher(self) -> None:
        """When buffer is full, publisher should block (not lose messages)."""
        pubsub = InMemoryPubSub(buffer_size=SMALL_BUFFER)
        publish_count = 0

        async def publisher() -> None:
            nonlocal publish_count
            # Subscribe first to create the buffer
            _sub = pubsub.subscribe("topic")
            for i in range(MESSAGE_COUNT_EXCEEDS_BUFFER):
                await pubsub.publish("topic", Message(payload=f"msg-{i}".encode()))
                publish_count += 1

        # Publisher should block after buffer fills
        with anyio.move_on_after(0.5):
            await publisher()

        # Should have published up to buffer size before blocking
        assert publish_count == SMALL_BUFFER
        await pubsub.close()


class TestCancellation:
    async def test_subscriber_cancellation_cleans_up(self) -> None:
        """Cancelled subscriber should clean up properly."""
        async with InMemoryPubSub() as pubsub:
            subscription_started = anyio.Event()

            async def subscriber() -> None:
                subscription_started.set()
                async for _msg in pubsub.subscribe("topic"):
                    pass  # Would run forever

            async with anyio.create_task_group() as tg:
                tg.start_soon(subscriber)
                await subscription_started.wait()
                # Cancel the task group
                tg.cancel_scope.cancel()

            # Should be able to publish without error (no zombie subscribers)
            await pubsub.publish("topic", Message(payload=b"after-cancel"))

    async def test_close_during_iteration(self) -> None:
        """Closing pubsub during iteration should not hang."""
        pubsub = InMemoryPubSub()
        iteration_started = anyio.Event()
        iteration_ended = anyio.Event()

        async def subscriber() -> None:
            iteration_started.set()
            async for _msg in pubsub.subscribe("topic"):
                pass
            iteration_ended.set()

        with anyio.fail_after(TIMEOUT_SECONDS):
            async with anyio.create_task_group() as tg:
                tg.start_soon(subscriber)
                await iteration_started.wait()
                await pubsub.close()
                await iteration_ended.wait()


class TestConcurrency:
    async def test_concurrent_publishers(self) -> None:
        """Multiple publishers should work concurrently."""
        async with InMemoryPubSub() as pubsub:
            received: list[Message] = []
            publishers_done = anyio.Event()
            publisher_count = 3
            messages_per_publisher = 5
            total_expected = publisher_count * messages_per_publisher

            async def subscriber() -> None:
                async for msg in pubsub.subscribe("topic"):
                    received.append(msg)
                    if len(received) >= total_expected:
                        break

            async def publisher(pub_id: int) -> None:
                for i in range(messages_per_publisher):
                    payload = f"pub-{pub_id}-msg-{i}".encode()
                    await pubsub.publish("topic", Message(payload=payload))

            async def run_publishers() -> None:
                async with anyio.create_task_group() as tg:
                    for i in range(publisher_count):
                        tg.start_soon(publisher, i)
                publishers_done.set()

            with anyio.fail_after(TIMEOUT_SECONDS):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(subscriber)
                    await anyio.sleep(0.01)
                    tg.start_soon(run_publishers)

            assert len(received) == total_expected

    async def test_concurrent_subscribers_same_topic(self) -> None:
        """Multiple subscribers on same topic each get all messages."""
        async with InMemoryPubSub() as pubsub:
            sub1_received: list[Message] = []
            sub2_received: list[Message] = []
            message_count = 5

            async def subscriber(received: list[Message]) -> None:
                async for msg in pubsub.subscribe("topic"):
                    received.append(msg)
                    if len(received) >= message_count:
                        break

            async def publisher() -> None:
                await anyio.sleep(0.01)
                for i in range(message_count):
                    await pubsub.publish("topic", Message(payload=f"msg-{i}".encode()))

            with anyio.fail_after(TIMEOUT_SECONDS):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(subscriber, sub1_received)
                    tg.start_soon(subscriber, sub2_received)
                    tg.start_soon(publisher)

            assert len(sub1_received) == message_count
            assert len(sub2_received) == message_count
