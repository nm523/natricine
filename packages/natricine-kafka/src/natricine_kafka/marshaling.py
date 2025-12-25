"""Marshaling between natricine Messages and Kafka records."""

from uuid import UUID

from natricine.pubsub import Message


def to_kafka_headers(
    message: Message,
    uuid_header: str,
) -> list[tuple[str, bytes]]:
    """Convert message metadata to Kafka headers."""
    headers: list[tuple[str, bytes]] = [
        (uuid_header, str(message.uuid).encode()),
    ]
    for key, value in message.metadata.items():
        headers.append((key, value.encode()))
    return headers


def from_kafka_headers(
    headers: list[tuple[str, bytes]],
    uuid_header: str,
) -> tuple[UUID | None, dict[str, str]]:
    """Extract UUID and metadata from Kafka headers."""
    uuid_value: UUID | None = None
    metadata: dict[str, str] = {}

    for key, value in headers:
        if key == uuid_header:
            uuid_value = UUID(value.decode())
        else:
            metadata[key] = value.decode()

    return uuid_value, metadata
