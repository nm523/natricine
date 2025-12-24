"""Tests for SNS Publisher and Subscriber."""

import asyncio

import aioboto3
import pytest
from natricine_aws import SNSConfig, SNSPublisher, SNSSubscriber

from natricine.pubsub import Message

pytestmark = pytest.mark.anyio


async def test_sns_publish_and_subscribe(
    session: aioboto3.Session,
    endpoint_url: str,
) -> None:
    """Test SNS pub/sub via SQS."""
    topic = "test-sns-topic"

    async with SNSPublisher(
        session,
        endpoint_url=endpoint_url,
    ) as publisher:
        config = SNSConfig(consumer_group="test-consumer")
        async with SNSSubscriber(
            session,
            config=config,
            endpoint_url=endpoint_url,
        ) as subscriber:
            # Set up subscription first (creates queue and subscribes)
            sub_iter = subscriber.subscribe(topic)

            async def receive_one():
                async for msg in sub_iter:
                    return msg
                return None

            # Start receiving (this will set up the subscription)
            receive_task = asyncio.create_task(receive_one())

            # Give time for subscription setup
            await asyncio.sleep(1)

            # Publish a message
            msg = Message(
                payload=b"sns hello",
                metadata={"sns_key": "sns_value"},
            )
            await publisher.publish(topic, msg)

            # Wait for message
            received = await asyncio.wait_for(receive_task, timeout=10)

            assert received is not None
            assert received.payload == b"sns hello"
            assert received.metadata == {"sns_key": "sns_value"}
            await received.ack()


async def test_sns_fanout_multiple_consumers(
    session: aioboto3.Session,
    endpoint_url: str,
) -> None:
    """Test SNS fan-out to multiple consumer groups."""
    topic = "test-fanout-topic"

    async with SNSPublisher(
        session,
        endpoint_url=endpoint_url,
    ) as publisher:
        # Two subscribers with different consumer groups
        config_a = SNSConfig(consumer_group="consumer-a")
        config_b = SNSConfig(consumer_group="consumer-b")

        async with SNSSubscriber(
            session,
            config=config_a,
            endpoint_url=endpoint_url,
        ) as subscriber_a:
            async with SNSSubscriber(
                session,
                config=config_b,
                endpoint_url=endpoint_url,
            ) as subscriber_b:
                # Start both subscriptions
                async def receive_from(sub):
                    async for msg in sub.subscribe(topic):
                        return msg
                    return None

                task_a = asyncio.create_task(receive_from(subscriber_a))
                task_b = asyncio.create_task(receive_from(subscriber_b))

                # Give time for subscription setup
                await asyncio.sleep(1)

                # Publish one message
                msg = Message(payload=b"fanout message")
                await publisher.publish(topic, msg)

                # Both consumers should receive the message
                received_a = await asyncio.wait_for(task_a, timeout=10)
                received_b = await asyncio.wait_for(task_b, timeout=10)

                assert received_a is not None
                assert received_b is not None
                assert received_a.payload == b"fanout message"
                assert received_b.payload == b"fanout message"

                await received_a.ack()
                await received_b.ack()
