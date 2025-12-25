"""Kafka publisher implementation."""

from aiokafka import AIOKafkaProducer

from natricine.pubsub import Message
from natricine_kafka.config import ProducerConfig
from natricine_kafka.marshaling import to_kafka_headers


class KafkaPublisher:
    """Publisher that sends messages to Kafka topics."""

    def __init__(self, config: ProducerConfig | None = None) -> None:
        """Initialize the Kafka publisher.

        Args:
            config: Producer configuration. Uses defaults if not provided.
        """
        self._config = config or ProducerConfig()
        self._producer: AIOKafkaProducer | None = None
        self._closed = False

    async def _get_producer(self) -> AIOKafkaProducer:
        """Get or create the Kafka producer."""
        if self._producer is None:
            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._config.bootstrap_servers,
                client_id=self._config.client_id,
                acks=self._config.acks,
                retry_backoff_ms=self._config.retry_backoff_ms,
            )
            await self._producer.start()
        return self._producer

    async def publish(self, topic: str, *messages: Message) -> None:
        """Publish messages to a Kafka topic."""
        if self._closed:
            msg = "Publisher is closed"
            raise RuntimeError(msg)

        producer = await self._get_producer()

        for message in messages:
            headers = to_kafka_headers(message, self._config.uuid_header)
            await producer.send_and_wait(
                topic,
                value=message.payload,
                headers=headers,
            )

    async def close(self) -> None:
        """Close the publisher.

        Sets closed flag immediately. Subsequent publish calls raise RuntimeError.
        """
        self._closed = True

    async def __aenter__(self) -> "KafkaPublisher":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        self._closed = True
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None
