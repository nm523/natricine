"""Kafka subscriber implementation."""

from collections.abc import AsyncIterator
from uuid import uuid4

from aiokafka import AIOKafkaConsumer, TopicPartition

from natricine.pubsub import Message
from natricine_kafka.config import ConsumerConfig
from natricine_kafka.marshaling import from_kafka_headers


class KafkaSubscriber:
    """Subscriber that consumes messages from Kafka topics."""

    def __init__(self, config: ConsumerConfig | None = None) -> None:
        """Initialize the Kafka subscriber.

        Args:
            config: Consumer configuration. Uses defaults if not provided.
        """
        self._config = config or ConsumerConfig()
        self._closed = False
        self._consumers: list[AIOKafkaConsumer] = []

    def subscribe(self, topic: str) -> AsyncIterator[Message]:
        """Subscribe to a Kafka topic.

        Each call creates a new consumer in the consumer group.
        """
        if self._closed:
            msg = "Subscriber is closed"
            raise RuntimeError(msg)

        return self._subscribe_iter(topic)

    async def _subscribe_iter(self, topic: str) -> AsyncIterator[Message]:
        """Consume messages from the topic."""
        consumer = AIOKafkaConsumer(
            topic,
            bootstrap_servers=self._config.bootstrap_servers,
            client_id=self._config.client_id,
            group_id=self._config.group_id,
            auto_offset_reset=self._config.auto_offset_reset,
            enable_auto_commit=self._config.enable_auto_commit,
            max_poll_records=self._config.max_poll_records,
        )
        self._consumers.append(consumer)

        try:
            await consumer.start()

            while not self._closed:
                # Fetch a batch of records
                records = await consumer.getmany(
                    timeout_ms=1000,
                    max_records=self._config.max_poll_records,
                )

                for tp, messages in records.items():
                    for record in messages:
                        message = self._to_message(consumer, tp, record)
                        yield message

        finally:
            await consumer.stop()
            if consumer in self._consumers:
                self._consumers.remove(consumer)

    def _to_message(
        self,
        consumer: AIOKafkaConsumer,
        tp: TopicPartition,
        record,
    ) -> Message:
        """Convert a Kafka record to a natricine Message."""
        headers = record.headers or []
        uuid_value, metadata = from_kafka_headers(headers, self._config.uuid_header)

        # Offset to commit on ack (next message)
        commit_offset = record.offset + 1

        async def ack_func() -> None:
            await consumer.commit({tp: commit_offset})

        async def nack_func() -> None:
            # Seek back to this message for redelivery
            consumer.seek(tp, record.offset)

        return Message(
            payload=record.value,
            metadata=metadata,
            uuid=uuid_value or uuid4(),
            _ack_func=ack_func,
            _nack_func=nack_func,
        )

    async def close(self) -> None:
        """Close the subscriber.

        Active iterators will exit after their current poll completes
        (up to timeout_ms, default 1000ms).
        """
        self._closed = True

    async def __aenter__(self) -> "KafkaSubscriber":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        await self.close()
