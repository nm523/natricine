"""Tests for InMemoryPubSub implementation."""

import anyio
import pytest

from natricine.pubsub import InMemoryPubSub, Message

pytestmark = pytest.mark.anyio

EXPECTED_TWO_MESSAGES = 2


class TestInMemoryPubSub:
    async def test_publish_and_subscribe(self) -> None:
        async with InMemoryPubSub() as pubsub:
            messages: list[Message] = []

            async def subscriber() -> None:
                async for msg in pubsub.subscribe("test-topic"):
                    messages.append(msg)
                    if len(messages) >= EXPECTED_TWO_MESSAGES:
                        break

            async def publisher() -> None:
                await anyio.sleep(0.01)  # Let subscriber start
                await pubsub.publish("test-topic", Message(payload=b"one"))
                await pubsub.publish("test-topic", Message(payload=b"two"))

            async with anyio.create_task_group() as tg:
                tg.start_soon(subscriber)
                tg.start_soon(publisher)

            assert len(messages) == EXPECTED_TWO_MESSAGES
            assert messages[0].payload == b"one"
            assert messages[1].payload == b"two"

    async def test_multiple_subscribers_receive_same_message(self) -> None:
        async with InMemoryPubSub() as pubsub:
            received1: list[Message] = []
            received2: list[Message] = []

            async def sub1() -> None:
                async for msg in pubsub.subscribe("topic"):
                    received1.append(msg)
                    break

            async def sub2() -> None:
                async for msg in pubsub.subscribe("topic"):
                    received2.append(msg)
                    break

            async def publisher() -> None:
                await anyio.sleep(0.01)
                await pubsub.publish("topic", Message(payload=b"broadcast"))

            async with anyio.create_task_group() as tg:
                tg.start_soon(sub1)
                tg.start_soon(sub2)
                tg.start_soon(publisher)

            assert len(received1) == 1
            assert len(received2) == 1
            assert received1[0].payload == b"broadcast"
            assert received2[0].payload == b"broadcast"

    async def test_publish_to_nonexistent_topic_is_noop(self) -> None:
        async with InMemoryPubSub() as pubsub:
            # Should not raise
            await pubsub.publish("no-subscribers", Message(payload=b"dropped"))

    async def test_close_stops_subscribers(self) -> None:
        pubsub = InMemoryPubSub()
        received: list[Message] = []
        stopped = anyio.Event()

        async def subscriber() -> None:
            async for msg in pubsub.subscribe("topic"):
                received.append(msg)
            stopped.set()

        async with anyio.create_task_group() as tg:
            tg.start_soon(subscriber)
            await anyio.sleep(0.01)
            await pubsub.close()
            with anyio.move_on_after(1):
                await stopped.wait()

        assert stopped.is_set()

    async def test_context_manager(self) -> None:
        async with InMemoryPubSub() as pubsub:
            assert not pubsub._closed
        assert pubsub._closed

    async def test_publish_after_close_raises(self) -> None:
        pubsub = InMemoryPubSub()
        await pubsub.close()
        with pytest.raises(RuntimeError, match="closed"):
            await pubsub.publish("topic", Message(payload=b"fail"))

    async def test_subscribe_after_close_raises(self) -> None:
        pubsub = InMemoryPubSub()
        await pubsub.close()
        with pytest.raises(RuntimeError, match="closed"):
            pubsub.subscribe("topic")
