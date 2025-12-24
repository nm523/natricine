"""Tests for OpenTelemetry tracing."""

import asyncio

import pytest
from natricine_otel import (
    TracingMiddleware,
    TracingPublisher,
    extract_context,
    inject_context,
    tracing,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind

from natricine.pubsub import InMemoryPubSub, Message

pytestmark = pytest.mark.anyio


class TestContextPropagation:
    """Tests for trace context injection and extraction."""

    def test_inject_empty_context(self):
        """Inject with no active span adds nothing."""
        msg = Message(payload=b"test", metadata={"existing": "value"})
        result = inject_context(msg)

        # No span active, so no traceparent added
        assert "existing" in result.metadata
        assert result.payload == msg.payload
        assert result.uuid == msg.uuid

    def test_inject_preserves_metadata(self):
        """Inject preserves existing metadata."""
        msg = Message(payload=b"test", metadata={"key": "value"})
        result = inject_context(msg)

        assert result.metadata["key"] == "value"

    def test_extract_empty_metadata(self):
        """Extract from empty metadata returns current context."""
        msg = Message(payload=b"test")
        ctx = extract_context(msg)
        # Should not raise, returns some context
        assert ctx is not None


class TestTracingMiddleware:
    """Tests for the tracing middleware."""

    async def test_creates_consumer_span(
        self,
        tracer_provider: TracerProvider,
        span_exporter: InMemorySpanExporter,
    ):
        """Middleware creates a CONSUMER span."""
        middleware = tracing(tracer_provider=tracer_provider)

        async def handler(msg: Message) -> list[Message] | None:
            return None

        wrapped = middleware(handler)
        await wrapped(Message(payload=b"test"))

        spans = span_exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].kind == SpanKind.CONSUMER
        assert spans[0].name == "process"

    async def test_span_includes_message_id(
        self,
        tracer_provider: TracerProvider,
        span_exporter: InMemorySpanExporter,
    ):
        """Span includes message.id attribute."""
        middleware = tracing(tracer_provider=tracer_provider)

        async def handler(msg: Message) -> list[Message] | None:
            return None

        msg = Message(payload=b"test")
        wrapped = middleware(handler)
        await wrapped(msg)

        spans = span_exporter.get_finished_spans()
        assert spans[0].attributes is not None
        assert spans[0].attributes["messaging.message.id"] == str(msg.uuid)

    async def test_span_includes_topic_from_metadata(
        self,
        tracer_provider: TracerProvider,
        span_exporter: InMemorySpanExporter,
    ):
        """Span includes topic when available in metadata."""
        middleware = tracing(
            tracer_provider=tracer_provider,
            topic_from_metadata="topic",
        )

        async def handler(msg: Message) -> list[Message] | None:
            return None

        msg = Message(payload=b"test", metadata={"topic": "my.topic"})
        wrapped = middleware(handler)
        await wrapped(msg)

        spans = span_exporter.get_finished_spans()
        assert spans[0].name == "process my.topic"
        assert spans[0].attributes is not None
        assert spans[0].attributes["messaging.destination.name"] == "my.topic"

    async def test_records_error_on_exception(
        self,
        tracer_provider: TracerProvider,
        span_exporter: InMemorySpanExporter,
    ):
        """Span records error status on exception."""
        middleware = tracing(tracer_provider=tracer_provider)

        async def handler(msg: Message) -> list[Message] | None:
            raise ValueError("test error")

        wrapped = middleware(handler)

        with pytest.raises(ValueError):
            await wrapped(Message(payload=b"test"))

        spans = span_exporter.get_finished_spans()
        assert spans[0].status.is_ok is False
        assert spans[0].attributes is not None
        assert spans[0].attributes["error.type"] == "ValueError"

    async def test_class_middleware_with_topic_extractor(
        self,
        tracer_provider: TracerProvider,
        span_exporter: InMemorySpanExporter,
    ):
        """TracingMiddleware class works with topic extractor."""
        middleware = TracingMiddleware(
            tracer_provider=tracer_provider,
            topic_extractor=lambda m: m.metadata.get("t"),
        )

        async def handler(msg: Message) -> list[Message] | None:
            return None

        msg = Message(payload=b"test", metadata={"t": "extracted.topic"})
        wrapped = middleware(handler)
        await wrapped(msg)

        spans = span_exporter.get_finished_spans()
        assert spans[0].name == "process extracted.topic"


class TestTracingPublisher:
    """Tests for the tracing publisher."""

    async def test_creates_producer_span(
        self,
        tracer_provider: TracerProvider,
        span_exporter: InMemorySpanExporter,
    ):
        """Publisher creates a PRODUCER span."""
        async with InMemoryPubSub() as pubsub:
            publisher = TracingPublisher(pubsub, tracer_provider=tracer_provider)

            await publisher.publish("test.topic", Message(payload=b"hello"))

        spans = span_exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].kind == SpanKind.PRODUCER
        assert spans[0].name == "send test.topic"

    async def test_span_includes_destination(
        self,
        tracer_provider: TracerProvider,
        span_exporter: InMemorySpanExporter,
    ):
        """Span includes destination name."""
        async with InMemoryPubSub() as pubsub:
            publisher = TracingPublisher(pubsub, tracer_provider=tracer_provider)

            await publisher.publish("orders.created", Message(payload=b"order"))

        spans = span_exporter.get_finished_spans()
        assert spans[0].attributes is not None
        assert spans[0].attributes["messaging.destination.name"] == "orders.created"

    async def test_injects_context_into_message(
        self,
        tracer_provider: TracerProvider,
        span_exporter: InMemorySpanExporter,
    ):
        """Publisher injects trace context into message metadata."""
        received: list[Message] = []

        async with InMemoryPubSub() as pubsub:
            publisher = TracingPublisher(pubsub, tracer_provider=tracer_provider)

            # Subscribe to receive the message
            async def collect():
                async for msg in pubsub.subscribe("topic"):
                    received.append(msg)
                    await msg.ack()
                    break

            task = asyncio.create_task(collect())
            await asyncio.sleep(0.01)

            await publisher.publish("topic", Message(payload=b"test"))
            await asyncio.wait_for(task, timeout=1)

        # Message should have traceparent in metadata
        assert len(received) == 1
        assert "traceparent" in received[0].metadata

    async def test_batch_span_includes_count(
        self,
        tracer_provider: TracerProvider,
        span_exporter: InMemorySpanExporter,
    ):
        """Batch publish includes message count attribute."""
        batch_size = 3
        async with InMemoryPubSub() as pubsub:
            publisher = TracingPublisher(pubsub, tracer_provider=tracer_provider)

            await publisher.publish(
                "topic",
                Message(payload=b"one"),
                Message(payload=b"two"),
                Message(payload=b"three"),
            )

        spans = span_exporter.get_finished_spans()
        assert spans[0].attributes is not None
        assert spans[0].attributes["messaging.batch.message_count"] == batch_size
