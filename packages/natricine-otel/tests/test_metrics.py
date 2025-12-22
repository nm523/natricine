"""Tests for OpenTelemetry metrics."""

import asyncio

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.util.types import AttributeValue

from natricine.otel import MetricsMiddleware, MetricsPublisher, metrics_middleware
from natricine.pubsub import InMemoryPubSub, Message

pytestmark = pytest.mark.anyio


@pytest.fixture
def metric_reader() -> InMemoryMetricReader:
    """Create an in-memory metric reader for testing."""
    return InMemoryMetricReader()


@pytest.fixture
def meter_provider(metric_reader: InMemoryMetricReader) -> MeterProvider:
    """Create a meter provider with in-memory reader."""
    return MeterProvider(metric_readers=[metric_reader])


def get_metric_value(
    metric_reader: InMemoryMetricReader,
    metric_name: str,
) -> tuple[float | int, dict[str, AttributeValue]]:
    """Get the value and attributes of a metric."""
    data = metric_reader.get_metrics_data()
    assert data is not None, "No metrics data available"
    for resource_metric in data.resource_metrics:
        for scope_metric in resource_metric.scope_metrics:
            for metric in scope_metric.metrics:
                if metric.name == metric_name:
                    # Get first data point
                    for point in metric.data.data_points:
                        # Histogram uses sum, Counter uses value
                        value: float | int = getattr(point, "value", None) or getattr(
                            point, "sum", 0
                        )
                        point_attrs = point.attributes or {}
                        attrs = {k: v for k, v in point_attrs.items()}
                        return value, attrs
    raise ValueError(f"Metric {metric_name} not found")


class TestMetricsMiddleware:
    """Tests for the metrics middleware."""

    async def test_records_consumed_message(
        self,
        meter_provider: MeterProvider,
        metric_reader: InMemoryMetricReader,
    ):
        """Middleware records consumed message count."""
        middleware = metrics_middleware(meter_provider=meter_provider)

        async def handler(msg: Message) -> list[Message] | None:
            return None

        wrapped = middleware(handler)
        await wrapped(Message(payload=b"test"))

        value, attrs = get_metric_value(
            metric_reader, "messaging.client.consumed.messages"
        )
        assert value == 1
        assert attrs["messaging.system"] == "natricine"
        assert attrs["messaging.operation.name"] == "process"

    async def test_records_process_duration(
        self,
        meter_provider: MeterProvider,
        metric_reader: InMemoryMetricReader,
    ):
        """Middleware records processing duration."""
        middleware = metrics_middleware(meter_provider=meter_provider)
        sleep_duration = 0.01

        async def handler(msg: Message) -> list[Message] | None:
            await asyncio.sleep(sleep_duration)
            return None

        wrapped = middleware(handler)
        await wrapped(Message(payload=b"test"))

        value, attrs = get_metric_value(metric_reader, "messaging.process.duration")
        assert value >= sleep_duration
        assert attrs["messaging.operation.name"] == "process"

    async def test_includes_topic_from_metadata(
        self,
        meter_provider: MeterProvider,
        metric_reader: InMemoryMetricReader,
    ):
        """Middleware includes topic when available."""
        middleware = metrics_middleware(
            meter_provider=meter_provider,
            topic_from_metadata="topic",
        )

        async def handler(msg: Message) -> list[Message] | None:
            return None

        msg = Message(payload=b"test", metadata={"topic": "my.topic"})
        wrapped = middleware(handler)
        await wrapped(msg)

        value, attrs = get_metric_value(
            metric_reader, "messaging.client.consumed.messages"
        )
        assert attrs["messaging.destination.name"] == "my.topic"

    async def test_records_error_type_on_exception(
        self,
        meter_provider: MeterProvider,
        metric_reader: InMemoryMetricReader,
    ):
        """Middleware records error type when handler raises."""
        middleware = metrics_middleware(meter_provider=meter_provider)

        async def handler(msg: Message) -> list[Message] | None:
            raise ValueError("test error")

        wrapped = middleware(handler)

        with pytest.raises(ValueError):
            await wrapped(Message(payload=b"test"))

        # Duration should still be recorded with error type
        value, attrs = get_metric_value(metric_reader, "messaging.process.duration")
        assert attrs["error.type"] == "ValueError"

    async def test_class_middleware_with_topic_extractor(
        self,
        meter_provider: MeterProvider,
        metric_reader: InMemoryMetricReader,
    ):
        """MetricsMiddleware class works with topic extractor."""
        middleware = MetricsMiddleware(
            meter_provider=meter_provider,
            topic_extractor=lambda m: m.metadata.get("t"),
        )

        async def handler(msg: Message) -> list[Message] | None:
            return None

        msg = Message(payload=b"test", metadata={"t": "extracted.topic"})
        wrapped = middleware(handler)
        await wrapped(msg)

        value, attrs = get_metric_value(
            metric_reader, "messaging.client.consumed.messages"
        )
        assert attrs["messaging.destination.name"] == "extracted.topic"


class TestMetricsPublisher:
    """Tests for the metrics publisher."""

    async def test_records_sent_message(
        self,
        meter_provider: MeterProvider,
        metric_reader: InMemoryMetricReader,
    ):
        """Publisher records sent message count."""
        async with InMemoryPubSub() as pubsub:
            publisher = MetricsPublisher(pubsub, meter_provider=meter_provider)

            await publisher.publish("test.topic", Message(payload=b"hello"))

        value, attrs = get_metric_value(
            metric_reader, "messaging.client.sent.messages"
        )
        assert value == 1
        assert attrs["messaging.system"] == "natricine"
        assert attrs["messaging.operation.name"] == "send"
        assert attrs["messaging.destination.name"] == "test.topic"

    async def test_records_operation_duration(
        self,
        meter_provider: MeterProvider,
        metric_reader: InMemoryMetricReader,
    ):
        """Publisher records operation duration."""
        async with InMemoryPubSub() as pubsub:
            publisher = MetricsPublisher(pubsub, meter_provider=meter_provider)

            await publisher.publish("topic", Message(payload=b"test"))

        value, attrs = get_metric_value(
            metric_reader, "messaging.client.operation.duration"
        )
        assert value >= 0
        assert attrs["messaging.operation.name"] == "send"

    async def test_batch_records_message_count(
        self,
        meter_provider: MeterProvider,
        metric_reader: InMemoryMetricReader,
    ):
        """Batch publish records correct message count."""
        batch_size = 3
        async with InMemoryPubSub() as pubsub:
            publisher = MetricsPublisher(pubsub, meter_provider=meter_provider)

            await publisher.publish(
                "topic",
                Message(payload=b"one"),
                Message(payload=b"two"),
                Message(payload=b"three"),
            )

        value, attrs = get_metric_value(
            metric_reader, "messaging.client.sent.messages"
        )
        assert value == batch_size
