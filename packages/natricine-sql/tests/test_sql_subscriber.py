"""Tests for SQLSubscriber."""

from uuid import uuid4

import anyio
import pytest

from natricine.pubsub import Message
from natricine.backends.sql import SQLConfig, SQLPublisher, SQLSubscriber


@pytest.mark.anyio
async def test_subscribe_receives_message(
    sqlite_connection, sqlite_dialect, sql_config
) -> None:
    """Test that subscriber receives published messages."""
    async with SQLPublisher(
        sqlite_connection, sqlite_dialect, sql_config
    ) as publisher:
        async with SQLSubscriber(
            sqlite_connection, sqlite_dialect, sql_config
        ) as subscriber:
            # Publish a message
            await publisher.publish("test-topic", Message(payload=b"hello"))

            # Subscribe and receive
            received = None
            with anyio.fail_after(2):
                async for msg in subscriber.subscribe("test-topic"):
                    received = msg
                    await msg.ack()
                    break

            assert received is not None
            assert received.payload == b"hello"


@pytest.mark.anyio
async def test_message_payload_preserved(
    sqlite_connection, sqlite_dialect, sql_config
) -> None:
    """Test that binary payload is preserved."""
    payload = bytes(range(256))  # All byte values

    async with SQLPublisher(
        sqlite_connection, sqlite_dialect, sql_config
    ) as publisher:
        async with SQLSubscriber(
            sqlite_connection, sqlite_dialect, sql_config
        ) as subscriber:
            await publisher.publish("test-topic", Message(payload=payload))

            with anyio.fail_after(2):
                async for msg in subscriber.subscribe("test-topic"):
                    assert msg.payload == payload
                    await msg.ack()
                    break


@pytest.mark.anyio
async def test_message_metadata_preserved(
    sqlite_connection, sqlite_dialect, sql_config
) -> None:
    """Test that metadata is preserved."""
    metadata = {"key": "value", "number": "42"}

    async with SQLPublisher(
        sqlite_connection, sqlite_dialect, sql_config
    ) as publisher:
        async with SQLSubscriber(
            sqlite_connection, sqlite_dialect, sql_config
        ) as subscriber:
            await publisher.publish(
                "test-topic", Message(payload=b"test", metadata=metadata)
            )

            with anyio.fail_after(2):
                async for msg in subscriber.subscribe("test-topic"):
                    assert msg.metadata["key"] == "value"
                    assert msg.metadata["number"] == "42"
                    await msg.ack()
                    break


@pytest.mark.anyio
async def test_message_uuid_preserved(
    sqlite_connection, sqlite_dialect, sql_config
) -> None:
    """Test that message UUID is preserved."""
    msg_uuid = uuid4()

    async with SQLPublisher(
        sqlite_connection, sqlite_dialect, sql_config
    ) as publisher:
        async with SQLSubscriber(
            sqlite_connection, sqlite_dialect, sql_config
        ) as subscriber:
            await publisher.publish(
                "test-topic", Message(payload=b"test", uuid=msg_uuid)
            )

            with anyio.fail_after(2):
                async for msg in subscriber.subscribe("test-topic"):
                    assert msg.uuid == msg_uuid
                    await msg.ack()
                    break


@pytest.mark.anyio
async def test_ack_removes_message(
    sqlite_connection, sqlite_dialect, sql_config
) -> None:
    """Test that acked messages are not redelivered."""
    async with SQLPublisher(
        sqlite_connection, sqlite_dialect, sql_config
    ) as publisher:
        async with SQLSubscriber(
            sqlite_connection, sqlite_dialect, sql_config
        ) as subscriber:
            await publisher.publish("test-topic", Message(payload=b"hello"))

            # Receive and ack
            with anyio.fail_after(2):
                async for msg in subscriber.subscribe("test-topic"):
                    await msg.ack()
                    break

            # Try to receive again - should timeout (no message)
            with pytest.raises(TimeoutError):
                with anyio.fail_after(0.5):
                    async for msg in subscriber.subscribe("test-topic"):
                        pytest.fail("Should not receive acked message")


@pytest.mark.anyio
async def test_nack_redelivers_message(
    sqlite_connection, sqlite_dialect
) -> None:
    """Test that nacked messages are redelivered."""
    config = SQLConfig(
        consumer_group="test",
        poll_interval=0.1,
        ack_deadline=1.0,  # Short deadline for testing
    )

    pub = SQLPublisher(sqlite_connection, sqlite_dialect, config)
    sub = SQLSubscriber(sqlite_connection, sqlite_dialect, config)
    async with pub, sub:
        await pub.publish("test-topic", Message(payload=b"hello"))

        delivery_count = 0
        expected_deliveries = 2
        with anyio.fail_after(3):
            async for msg in sub.subscribe("test-topic"):
                delivery_count += 1
                if delivery_count == 1:
                    await msg.nack()  # Reject first delivery
                else:
                    await msg.ack()  # Accept redelivery
                    break

        assert delivery_count == expected_deliveries


@pytest.mark.anyio
async def test_subscribe_after_close_raises(sqlite_subscriber: SQLSubscriber) -> None:
    """Test that subscribing after close raises RuntimeError."""
    await sqlite_subscriber.close()
    with pytest.raises(RuntimeError, match="closed"):
        async for _ in sqlite_subscriber.subscribe("test-topic"):
            pass


@pytest.mark.anyio
async def test_multiple_messages_in_order(
    sqlite_connection, sqlite_dialect
) -> None:
    """Test that multiple messages are received in order."""
    config = SQLConfig(
        consumer_group="test",
        poll_interval=0.1,
        ack_deadline=1.0,
    )

    num_messages = 3
    pub = SQLPublisher(sqlite_connection, sqlite_dialect, config)
    sub = SQLSubscriber(sqlite_connection, sqlite_dialect, config)
    async with pub, sub:
        # Publish multiple messages
        for i in range(num_messages):
            payload = f"msg{i}".encode()
            await pub.publish("test-topic", Message(payload=payload))

        # Receive all messages
        received = []
        with anyio.fail_after(3):
            async for msg in sub.subscribe("test-topic"):
                received.append(msg.payload)
                await msg.ack()
                if len(received) == num_messages:
                    break

        assert received == [b"msg0", b"msg1", b"msg2"]
