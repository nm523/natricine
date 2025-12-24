"""Redis Streams publisher implementation."""

from redis.asyncio import Redis

from natricine.pubsub import Message


class RedisStreamPublisher:
    """Publisher that writes messages to Redis Streams using XADD."""

    def __init__(
        self,
        redis: Redis,
        maxlen: int | None = None,
    ) -> None:
        """Initialize the publisher.

        Args:
            redis: Async Redis client.
            maxlen: Optional max stream length (uses MAXLEN ~).
        """
        self._redis = redis
        self._maxlen = maxlen
        self._closed = False

    async def publish(self, topic: str, *messages: Message) -> None:
        """Publish messages to a Redis stream.

        The topic name becomes the stream key.
        """
        if self._closed:
            msg = "Publisher is closed"
            raise RuntimeError(msg)

        for message in messages:
            fields = {
                "uuid": str(message.uuid),
                "payload": message.payload,
            }
            # Add metadata as separate fields
            for key, value in message.metadata.items():
                fields[f"meta:{key}"] = value

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
