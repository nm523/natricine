"""Tests for SQLPublisher."""

from uuid import uuid4

import pytest
from natricine_sql import SQLPublisher

from natricine.pubsub import Message


@pytest.mark.anyio
async def test_publish_single_message(sqlite_publisher: SQLPublisher) -> None:
    """Test publishing a single message."""
    msg = Message(payload=b"hello")
    await sqlite_publisher.publish("test-topic", msg)


@pytest.mark.anyio
async def test_publish_multiple_messages(sqlite_publisher: SQLPublisher) -> None:
    """Test publishing multiple messages in one call."""
    messages = [
        Message(payload=b"msg1"),
        Message(payload=b"msg2"),
        Message(payload=b"msg3"),
    ]
    await sqlite_publisher.publish("test-topic", *messages)


@pytest.mark.anyio
async def test_publish_with_metadata(sqlite_publisher: SQLPublisher) -> None:
    """Test publishing a message with metadata."""
    msg = Message(
        payload=b"hello",
        metadata={"key": "value", "foo": "bar"},
    )
    await sqlite_publisher.publish("test-topic", msg)


@pytest.mark.anyio
async def test_publish_preserves_uuid(sqlite_publisher: SQLPublisher) -> None:
    """Test that message UUID is preserved."""
    msg_uuid = uuid4()
    msg = Message(payload=b"hello", uuid=msg_uuid)
    await sqlite_publisher.publish("test-topic", msg)
    # UUID preservation is verified in subscriber tests


@pytest.mark.anyio
async def test_publish_to_multiple_topics(sqlite_publisher: SQLPublisher) -> None:
    """Test publishing to different topics creates separate tables."""
    await sqlite_publisher.publish("topic-a", Message(payload=b"a"))
    await sqlite_publisher.publish("topic-b", Message(payload=b"b"))


@pytest.mark.anyio
async def test_publish_after_close_raises(sqlite_publisher: SQLPublisher) -> None:
    """Test that publishing after close raises RuntimeError."""
    await sqlite_publisher.close()
    with pytest.raises(RuntimeError, match="closed"):
        await sqlite_publisher.publish("test-topic", Message(payload=b"hello"))
