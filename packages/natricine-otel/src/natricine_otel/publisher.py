"""Tracing publisher decorator."""

from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode, TracerProvider

from natricine.pubsub import Message, Publisher
from natricine_otel.propagation import inject_context


class TracingPublisher:
    """Publisher wrapper that creates spans and injects trace context.

    Wraps a publisher to:
    1. Create a PRODUCER span for each publish
    2. Inject trace context into message metadata

    Example:
        publisher = TracingPublisher(my_publisher)
        await publisher.publish("topic", message)  # Span created, context injected
    """

    def __init__(
        self,
        publisher: Publisher,
        tracer_provider: TracerProvider | None = None,
        messaging_system: str = "natricine",
    ) -> None:
        self._publisher = publisher
        provider = tracer_provider or trace.get_tracer_provider()
        self._tracer = provider.get_tracer("natricine.otel")
        self._system = messaging_system

    async def publish(self, topic: str, *messages: Message) -> None:
        """Publish messages with tracing."""
        span_name = f"send {topic}"

        with self._tracer.start_as_current_span(
            span_name,
            kind=SpanKind.PRODUCER,
            attributes={
                "messaging.system": self._system,
                "messaging.operation.type": "send",
                "messaging.operation.name": "send",
                "messaging.destination.name": topic,
            },
        ) as span:
            try:
                # Inject context into each message
                traced_messages = tuple(inject_context(msg) for msg in messages)

                # Add message count if batch
                if len(traced_messages) > 1:
                    span.set_attribute(
                        "messaging.batch.message_count", len(traced_messages)
                    )
                elif traced_messages:
                    span.set_attribute(
                        "messaging.message.id", str(traced_messages[0].uuid)
                    )

                await self._publisher.publish(topic, *traced_messages)
                span.set_status(Status(StatusCode.OK))
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.set_attribute("error.type", type(e).__name__)
                raise

    async def close(self) -> None:
        """Close the underlying publisher."""
        await self._publisher.close()

    async def __aenter__(self) -> "TracingPublisher":
        await self._publisher.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        await self._publisher.__aexit__(exc_type, exc_val, exc_tb)
