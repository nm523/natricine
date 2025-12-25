"""Redis Streams subscriber implementation."""

from collections.abc import AsyncIterator
from uuid import UUID

import msgpack
from redis.asyncio import Redis
from redis.exceptions import ResponseError

from natricine.pubsub import Message

CONSUMER_GROUP_EXISTS_ERROR = "BUSYGROUP"

# Default field names (natricine-prefixed for identification)
DEFAULT_UUID_KEY = "_natricine_message_uuid"
DEFAULT_PAYLOAD_KEY = "payload"
DEFAULT_METADATA_KEY = "metadata"


class RedisStreamSubscriber:
    """Subscriber that reads from Redis Streams using consumer groups."""

    def __init__(
        self,
        redis: Redis,
        group_name: str,
        consumer_name: str,
        block_ms: int = 5000,
        count: int = 10,
        *,
        uuid_key: str = DEFAULT_UUID_KEY,
        payload_key: str = DEFAULT_PAYLOAD_KEY,
        metadata_key: str = DEFAULT_METADATA_KEY,
    ) -> None:
        """Initialize the subscriber.

        Args:
            redis: Async Redis client.
            group_name: Consumer group name.
            consumer_name: Unique consumer name within the group.
            block_ms: How long to block waiting for messages (milliseconds).
            count: Max messages to read per batch.
            uuid_key: Field name for message UUID.
            payload_key: Field name for message payload.
            metadata_key: Field name for msgpack-encoded metadata.
        """
        self._redis = redis
        self._group_name = group_name
        self._consumer_name = consumer_name
        self._block_ms = block_ms
        self._count = count
        self._uuid_key = uuid_key
        self._payload_key = payload_key
        self._metadata_key = metadata_key
        self._closed = False

    def subscribe(self, topic: str) -> AsyncIterator[Message]:
        """Subscribe to a Redis stream.

        Creates the consumer group if it doesn't exist.
        """
        if self._closed:
            msg = "Subscriber is closed"
            raise RuntimeError(msg)

        return self._subscribe_iter(topic)

    async def _ensure_group(self, topic: str) -> None:
        """Ensure the consumer group exists."""
        try:
            await self._redis.xgroup_create(
                topic,
                self._group_name,
                id="0",
                mkstream=True,
            )
        except ResponseError as e:
            if CONSUMER_GROUP_EXISTS_ERROR not in str(e):
                raise

    async def _subscribe_iter(self, topic: str) -> AsyncIterator[Message]:
        """Iterate over messages from the stream."""
        await self._ensure_group(topic)

        while not self._closed:
            # First, check for pending messages (redelivery)
            pending_response = await self._redis.xreadgroup(
                groupname=self._group_name,
                consumername=self._consumer_name,
                streams={topic: "0"},  # "0" reads pending messages
                count=self._count,
                block=0,  # Don't block for pending - check quickly
            )

            if pending_response:
                for _stream_name, messages in pending_response:
                    for message_id, fields in messages:
                        message = self._parse_message(topic, message_id, fields)
                        yield message

            # Then read new messages
            response = await self._redis.xreadgroup(
                groupname=self._group_name,
                consumername=self._consumer_name,
                streams={topic: ">"},  # ">" reads only new messages
                count=self._count,
                block=self._block_ms,
            )

            if not response:
                continue

            for _stream_name, messages in response:
                for message_id, fields in messages:
                    message = self._parse_message(topic, message_id, fields)
                    yield message

    def _parse_message(
        self,
        topic: str,
        message_id: bytes,
        fields: dict[bytes, bytes],
    ) -> Message:
        """Parse Redis stream entry into a Message.

        Metadata is msgpack-encoded.
        """
        # Decode field keys
        decoded = {k.decode(): v for k, v in fields.items()}

        uuid_raw = decoded.get(self._uuid_key, b"")
        uuid_str = uuid_raw.decode() if isinstance(uuid_raw, bytes) else uuid_raw
        payload = decoded.get(self._payload_key, b"")
        if isinstance(payload, str):
            payload = payload.encode()

        # Decode msgpack metadata
        metadata: dict[str, str] = {}
        metadata_raw = decoded.get(self._metadata_key)
        if metadata_raw:
            unpacked = msgpack.unpackb(metadata_raw, raw=False)
            if isinstance(unpacked, dict):
                metadata = {str(k): str(v) for k, v in unpacked.items()}

        # Create ack/nack functions bound to this message
        stream_key = topic
        mid = message_id.decode() if isinstance(message_id, bytes) else message_id

        async def ack_func() -> None:
            await self._redis.xack(stream_key, self._group_name, mid)

        async def nack_func() -> None:
            # For nack, we don't ack - message stays pending for redelivery
            # Could also use XCLAIM to move to dead letter stream
            pass

        return Message(
            payload=payload,
            metadata=metadata,
            uuid=UUID(uuid_str) if uuid_str else None,  # type: ignore[arg-type]
            _ack_func=ack_func,
            _nack_func=nack_func,
        )

    async def close(self) -> None:
        """Close the subscriber."""
        self._closed = True

    async def __aenter__(self) -> "RedisStreamSubscriber":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        await self.close()
