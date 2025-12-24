"""Integration tests for Redis Streams pub/sub.

These tests require a running Redis instance.
Set REDIS_URL environment variable or use default localhost:6379.
"""

import uuid

import pytest
from natricine_redis import RedisStreamPublisher, RedisStreamSubscriber

from natricine.pubsub import Message

pytestmark = [pytest.mark.anyio, pytest.mark.containers]

MESSAGES_PER_CONSUMER = 2
EXPECTED_THREE_MESSAGES = 3
EXPECTED_FOUR_MESSAGES = 4


class TestRedisStreamPublisher:
    async def test_publish_message(self, redis_client, clean_stream) -> None:
        stream = clean_stream(f"test:publish:{uuid.uuid4()}")

        async with RedisStreamPublisher(redis_client) as publisher:
            msg = Message(payload=b"hello world")
            await publisher.publish(stream, msg)

        # Verify message was added
        messages = await redis_client.xrange(stream)
        assert len(messages) == 1
        _, fields = messages[0]
        assert fields[b"payload"] == b"hello world"

    async def test_publish_with_metadata(self, redis_client, clean_stream) -> None:
        stream = clean_stream(f"test:metadata:{uuid.uuid4()}")

        async with RedisStreamPublisher(redis_client) as publisher:
            msg = Message(
                payload=b"test",
                metadata={"correlation_id": "abc123", "source": "test"},
            )
            await publisher.publish(stream, msg)

        messages = await redis_client.xrange(stream)
        assert len(messages) == 1
        _, fields = messages[0]
        assert fields[b"meta:correlation_id"] == b"abc123"
        assert fields[b"meta:source"] == b"test"

    async def test_publish_multiple(self, redis_client, clean_stream) -> None:
        stream = clean_stream(f"test:multi:{uuid.uuid4()}")

        async with RedisStreamPublisher(redis_client) as publisher:
            await publisher.publish(
                stream,
                Message(payload=b"one"),
                Message(payload=b"two"),
                Message(payload=b"three"),
            )

        messages = await redis_client.xrange(stream)
        assert len(messages) == EXPECTED_THREE_MESSAGES


class TestRedisStreamSubscriber:
    async def test_subscribe_receives_message(self, redis_client, clean_stream) -> None:
        stream = clean_stream(f"test:sub:{uuid.uuid4()}")
        group = f"group:{uuid.uuid4()}"
        consumer = "consumer1"

        # Publish first
        publisher = RedisStreamPublisher(redis_client)
        await publisher.publish(stream, Message(payload=b"test message"))

        # Subscribe and receive
        subscriber = RedisStreamSubscriber(redis_client, group, consumer, block_ms=100)
        received: list[Message] = []

        async for msg in subscriber.subscribe(stream):
            received.append(msg)
            await msg.ack()
            break  # Stop after first message

        assert len(received) == 1
        assert received[0].payload == b"test message"

    async def test_subscribe_with_metadata(self, redis_client, clean_stream) -> None:
        stream = clean_stream(f"test:submeta:{uuid.uuid4()}")
        group = f"group:{uuid.uuid4()}"

        publisher = RedisStreamPublisher(redis_client)
        await publisher.publish(
            stream,
            Message(payload=b"test", metadata={"key": "value"}),
        )

        subscriber = RedisStreamSubscriber(redis_client, group, "c1", block_ms=100)

        async for msg in subscriber.subscribe(stream):
            assert msg.metadata.get("key") == "value"
            await msg.ack()
            break

    async def test_ack_removes_from_pending(self, redis_client, clean_stream) -> None:
        stream = clean_stream(f"test:ack:{uuid.uuid4()}")
        group = f"group:{uuid.uuid4()}"

        publisher = RedisStreamPublisher(redis_client)
        await publisher.publish(stream, Message(payload=b"ack me"))

        subscriber = RedisStreamSubscriber(redis_client, group, "c1", block_ms=100)

        async for msg in subscriber.subscribe(stream):
            # Before ack, message should be pending
            pending_before = await redis_client.xpending(stream, group)

            await msg.ack()

            # After ack, pending count should decrease
            pending_after = await redis_client.xpending(stream, group)
            assert pending_after["pending"] < pending_before["pending"]
            break

    async def test_multiple_consumers_in_group(
        self, redis_client, clean_stream
    ) -> None:
        stream = clean_stream(f"test:consumers:{uuid.uuid4()}")
        group = f"group:{uuid.uuid4()}"

        # Publish multiple messages
        publisher = RedisStreamPublisher(redis_client)
        for i in range(4):
            await publisher.publish(stream, Message(payload=f"msg{i}".encode()))

        # Two consumers in same group
        sub1 = RedisStreamSubscriber(redis_client, group, "c1", block_ms=100, count=2)
        sub2 = RedisStreamSubscriber(redis_client, group, "c2", block_ms=100, count=2)

        c1_msgs: list[Message] = []
        c2_msgs: list[Message] = []

        # Each consumer reads some messages
        count = 0
        async for msg in sub1.subscribe(stream):
            c1_msgs.append(msg)
            await msg.ack()
            count += 1
            if count >= MESSAGES_PER_CONSUMER:
                break

        count = 0
        async for msg in sub2.subscribe(stream):
            c2_msgs.append(msg)
            await msg.ack()
            count += 1
            if count >= MESSAGES_PER_CONSUMER:
                break

        # Messages should be distributed (not duplicated)
        total = len(c1_msgs) + len(c2_msgs)
        assert total == EXPECTED_FOUR_MESSAGES
