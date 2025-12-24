"""Tracing middleware for natricine Router."""

from collections.abc import Callable

from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode, TracerProvider

from natricine.pubsub import Message
from natricine.router.types import HandlerFunc, Middleware
from natricine_otel.propagation import extract_context


def tracing(
    tracer_provider: TracerProvider | None = None,
    messaging_system: str = "natricine",
    topic_from_metadata: str | None = None,
) -> Middleware:
    """Middleware that creates spans for message processing.

    Args:
        tracer_provider: OpenTelemetry TracerProvider. Uses global if not set.
        messaging_system: Value for messaging.system attribute.
        topic_from_metadata: Optional metadata key to get topic name from.
            If set, the value is used for messaging.destination.name.

    Example:
        router.add_middleware(tracing())

        # With topic in metadata:
        router.add_middleware(tracing(topic_from_metadata="topic"))
    """
    provider = tracer_provider or trace.get_tracer_provider()
    tracer = provider.get_tracer("natricine.otel")

    def middleware(next_handler: HandlerFunc) -> HandlerFunc:
        async def handler(msg: Message) -> list[Message] | None:
            # Extract parent context from message
            parent_ctx = extract_context(msg)

            # Build span attributes
            attributes: dict[str, str] = {
                "messaging.system": messaging_system,
                "messaging.operation.type": "process",
                "messaging.operation.name": "process",
                "messaging.message.id": str(msg.uuid),
            }

            # Get topic from metadata if configured
            topic = None
            if topic_from_metadata and topic_from_metadata in msg.metadata:
                topic = msg.metadata[topic_from_metadata]
                attributes["messaging.destination.name"] = topic

            span_name = f"process {topic}" if topic else "process"

            with tracer.start_as_current_span(
                span_name,
                context=parent_ctx,
                kind=SpanKind.CONSUMER,
                attributes=attributes,
            ) as span:
                try:
                    result = await next_handler(msg)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.set_attribute("error.type", type(e).__name__)
                    raise

        return handler

    return middleware


class TracingMiddleware:
    """Class-based tracing middleware for more control.

    Use this when you need to customize span attributes or have
    a topic extractor function.

    Example:
        middleware = TracingMiddleware(
            topic_extractor=lambda msg: msg.metadata.get("topic")
        )
        router.add_middleware(middleware)
    """

    def __init__(
        self,
        tracer_provider: TracerProvider | None = None,
        messaging_system: str = "natricine",
        topic_extractor: Callable[[Message], str | None] | None = None,
    ) -> None:
        provider = tracer_provider or trace.get_tracer_provider()
        self._tracer = provider.get_tracer("natricine.otel")
        self._system = messaging_system
        self._topic_extractor = topic_extractor

    def __call__(self, next_handler: HandlerFunc) -> HandlerFunc:
        async def handler(msg: Message) -> list[Message] | None:
            parent_ctx = extract_context(msg)

            attributes: dict[str, str] = {
                "messaging.system": self._system,
                "messaging.operation.type": "process",
                "messaging.operation.name": "process",
                "messaging.message.id": str(msg.uuid),
            }

            topic = None
            if self._topic_extractor:
                topic = self._topic_extractor(msg)
                if topic:
                    attributes["messaging.destination.name"] = topic

            span_name = f"process {topic}" if topic else "process"

            with self._tracer.start_as_current_span(
                span_name,
                context=parent_ctx,
                kind=SpanKind.CONSUMER,
                attributes=attributes,
            ) as span:
                try:
                    result = await next_handler(msg)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.set_attribute("error.type", type(e).__name__)
                    raise

        return handler
