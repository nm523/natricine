"""Trace context propagation via message metadata."""

from opentelemetry import propagate
from opentelemetry.context import Context

from natricine.pubsub import Message


def inject_context(message: Message) -> Message:
    """Inject current trace context into message metadata.

    Returns a new Message with trace context headers added to metadata.
    """
    carrier: dict[str, str] = {}
    propagate.inject(carrier)

    if not carrier:
        return message

    return Message(
        uuid=message.uuid,
        payload=message.payload,
        metadata={**message.metadata, **carrier},
    )


def extract_context(message: Message) -> Context:
    """Extract trace context from message metadata.

    Returns the extracted Context, or the current context if none found.
    """
    return propagate.extract(message.metadata)
