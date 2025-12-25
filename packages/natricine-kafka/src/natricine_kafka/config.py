"""Configuration for Kafka publisher and subscriber."""

from dataclasses import dataclass

# Default UUID header key (natricine-prefixed for identification)
DEFAULT_UUID_HEADER = "_natricine_message_uuid"


@dataclass
class KafkaConfig:
    """Configuration for Kafka publisher/subscriber."""

    bootstrap_servers: str = "localhost:9092"
    """Comma-separated list of Kafka broker addresses."""

    client_id: str = "natricine"
    """Client identifier for Kafka connections."""

    uuid_header: str = DEFAULT_UUID_HEADER
    """Header key for message UUID."""


@dataclass
class ProducerConfig(KafkaConfig):
    """Configuration for Kafka producer."""

    acks: str = "all"
    """Acknowledgment level: 0, 1, or 'all'."""

    retry_backoff_ms: int = 100
    """Milliseconds to wait before retrying a failed request."""


@dataclass
class ConsumerConfig(KafkaConfig):
    """Configuration for Kafka consumer."""

    group_id: str = "natricine"
    """Consumer group identifier."""

    auto_offset_reset: str = "earliest"
    """Where to start reading: 'earliest', 'latest', or 'none'."""

    enable_auto_commit: bool = False
    """Disable auto-commit; we commit on ack."""

    max_poll_records: int = 10
    """Maximum records to fetch per poll."""
