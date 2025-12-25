"""Redis Streams publisher implementation."""

import msgpack
from redis.asyncio import Redis

from natricine.pubsub import Message

# Default field names (natricine-prefixed for identification)
DEFAULT_UUID_KEY = "_natricine_message_uuid"
DEFAULT_PAYLOAD_KEY = "payload"
DEFAULT_METADATA_KEY = "metadata"


class RedisStreamPublisher:
    """Publisher that writes messages to Redis Streams using XADD."""

    def __init__(
        self,
        redis: Redis,
        maxlen: int | None = None,
        *,
        uuid_key: str = DEFAULT_UUID_KEY,
        payload_key: str = DEFAULT_PAYLOAD_KEY,
        metadata_key: str = DEFAULT_METADATA_KEY,
    ) -> None:
        """Initialize the publisher.

        Args:
            redis: Async Redis client.
            maxlen: Optional max stream length (uses MAXLEN ~).
            uuid_key: Field name for message UUID.
            payload_key: Field name for message payload.
            metadata_key: Field name for msgpack-encoded metadata.
        """
        self._redis = redis
        self._maxlen = maxlen
        self._uuid_key = uuid_key
        self._payload_key = payload_key
        self._metadata_key = metadata_key
        self._closed = False

    async def publish(self, topic: str, *messages: Message) -> None:
        """Publish messages to a Redis stream.

        The topic name becomes the stream key.
        Metadata is msgpack-encoded for efficiency.
        """
        if self._closed:
            msg = "Publisher is closed"
            raise RuntimeError(msg)

        for message in messages:
            fields: dict[str, str | bytes] = {
                self._uuid_key: str(message.uuid),
                self._payload_key: message.payload,
            }
            if message.metadata:
                fields[self._metadata_key] = msgpack.packb(message.metadata)

            await self._redis.xadd(
                topic,
                fields,  # type: ignore[arg-type]
                maxlen=self._maxlen,
                approximate=True if self._maxlen else False,
            )

    async def close(self) -> None:
        """Close the publisher."""
        self._closed = True

    async def __aenter__(self) -> "RedisStreamPublisher":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        await self.close()
