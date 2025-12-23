"""Tests for SQS Publisher and Subscriber."""

import asyncio

import aioboto3
import pytest

from natricine.aws import SQSPublisher, SQSSubscriber
from natricine.pubsub import Message

pytestmark = pytest.mark.anyio


async def test_sqs_publish_and_subscribe(
    session: aioboto3.Session,
    endpoint_url: str,
) -> None:
    """Test basic publish and subscribe flow."""
    topic = "test-queue"

    async with SQSPublisher(
        session,
        endpoint_url=endpoint_url,
    ) as publisher:
        async with SQSSubscriber(
            session,
            endpoint_url=endpoint_url,
        ) as subscriber:
            # Publish a message
            msg = Message(
                payload=b"hello world",
                metadata={"key": "value"},
            )
            await publisher.publish(topic, msg)

            # Subscribe and receive
            received = []
            async for message in subscriber.subscribe(topic):
                received.append(message)
                await message.ack()
                break  # Only expect one message

            assert len(received) == 1
            assert received[0].payload == b"hello world"
            assert received[0].metadata == {"key": "value"}
            assert received[0].uuid == msg.uuid


async def test_sqs_multiple_messages(
    session: aioboto3.Session,
    endpoint_url: str,
) -> None:
    """Test publishing multiple messages."""
    topic = "test-multi-queue"
    msg_count = 3

    async with SQSPublisher(
        session,
        endpoint_url=endpoint_url,
    ) as publisher:
        async with SQSSubscriber(
            session,
            endpoint_url=endpoint_url,
        ) as subscriber:
            # Publish multiple messages
            messages = [Message(payload=f"msg-{i}".encode()) for i in range(msg_count)]
            await publisher.publish(topic, *messages)

            # Receive all messages
            received = []
            async for message in subscriber.subscribe(topic):
                received.append(message)
                await message.ack()
                if len(received) >= msg_count:
                    break

            assert len(received) == msg_count
            payloads = {m.payload for m in received}
            assert payloads == {b"msg-0", b"msg-1", b"msg-2"}


async def test_sqs_nack_redelivers(
    session: aioboto3.Session,
    endpoint_url: str,
) -> None:
    """Test that nack makes message available for redelivery."""
    topic = "test-nack-queue"

    async with SQSPublisher(
        session,
        endpoint_url=endpoint_url,
    ) as publisher:
        async with SQSSubscriber(
            session,
            endpoint_url=endpoint_url,
        ) as subscriber:
            # Publish a message
            msg = Message(payload=b"retry me")
            await publisher.publish(topic, msg)

            # First receive - nack it
            first_receive = None
            async for message in subscriber.subscribe(topic):
                first_receive = message
                await message.nack()
                break

            # Second receive - should get same message
            # Small delay to allow visibility timeout reset
            await asyncio.sleep(0.5)

            second_receive = None
            async for message in subscriber.subscribe(topic):
                second_receive = message
                await message.ack()
                break

            assert first_receive is not None
            assert second_receive is not None
            assert first_receive.payload == second_receive.payload == b"retry me"


async def test_sqs_binary_payload(
    session: aioboto3.Session,
    endpoint_url: str,
) -> None:
    """Test binary payload handling."""
    topic = "test-binary-queue"

    async with SQSPublisher(
        session,
        endpoint_url=endpoint_url,
    ) as publisher:
        async with SQSSubscriber(
            session,
            endpoint_url=endpoint_url,
        ) as subscriber:
            # Publish binary data (non-UTF8)
            binary_data = bytes(range(256))
            msg = Message(payload=binary_data)
            await publisher.publish(topic, msg)

            # Receive
            async for message in subscriber.subscribe(topic):
                assert message.payload == binary_data
                await message.ack()
                break
