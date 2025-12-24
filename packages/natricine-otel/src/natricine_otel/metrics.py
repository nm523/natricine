"""Metrics middleware and publisher decorator."""

import time
from collections.abc import Callable
from typing import Any

from opentelemetry import metrics
from opentelemetry.metrics import MeterProvider

from natricine.pubsub import Message, Publisher
from natricine.router import HandlerFunc, Middleware
from natricine_otel.propagation import inject_context


def metrics_middleware(
    meter_provider: MeterProvider | None = None,
    messaging_system: str = "natricine",
    topic_from_metadata: str | None = None,
) -> Middleware:
    """Create a metrics middleware for message processing.

    Tracks:
    - messaging.process.duration: Processing time histogram
    - messaging.client.consumed.messages: Message count

    Args:
        meter_provider: OTEL MeterProvider (uses global if not provided).
        messaging_system: Value for messaging.system attribute.
        topic_from_metadata: Metadata key containing topic name.

    Returns:
        Middleware function.
    """
    provider = meter_provider or metrics.get_meter_provider()
    meter = provider.get_meter("natricine.otel")

    process_duration = meter.create_histogram(
        "messaging.process.duration",
        unit="s",
        description="Duration of processing operation",
    )
    consumed_messages = meter.create_counter(
        "messaging.client.consumed.messages",
        unit="{message}",
        description="Number of messages delivered to the application",
    )

    def middleware(handler: HandlerFunc) -> HandlerFunc:
        async def wrapper(msg: Message) -> list[Message] | None:
            topic = None
            if topic_from_metadata:
                topic = msg.metadata.get(topic_from_metadata)

            attributes: dict[str, Any] = {
                "messaging.system": messaging_system,
                "messaging.operation.name": "process",
            }
            if topic:
                attributes["messaging.destination.name"] = topic

            start = time.perf_counter()
            try:
                result = await handler(msg)
                consumed_messages.add(1, attributes)
                return result
            except Exception as e:
                attributes["error.type"] = type(e).__name__
                raise
            finally:
                duration = time.perf_counter() - start
                process_duration.record(duration, attributes)

        return wrapper

    return middleware


class MetricsMiddleware:
    """Class-based metrics middleware with topic extractor support.

    Example:
        middleware = MetricsMiddleware(
            topic_extractor=lambda m: m.metadata.get("topic"),
        )
        router.add_middleware(middleware)
    """

    def __init__(
        self,
        meter_provider: MeterProvider | None = None,
        messaging_system: str = "natricine",
        topic_extractor: Callable[[Message], str | None] | None = None,
    ) -> None:
        provider = meter_provider or metrics.get_meter_provider()
        meter = provider.get_meter("natricine.otel")

        self._process_duration = meter.create_histogram(
            "messaging.process.duration",
            unit="s",
            description="Duration of processing operation",
        )
        self._consumed_messages = meter.create_counter(
            "messaging.client.consumed.messages",
            unit="{message}",
            description="Number of messages delivered to the application",
        )
        self._system = messaging_system
        self._topic_extractor = topic_extractor

    def __call__(self, handler: HandlerFunc) -> HandlerFunc:
        async def wrapper(msg: Message) -> list[Message] | None:
            topic = None
            if self._topic_extractor:
                topic = self._topic_extractor(msg)

            attributes: dict[str, Any] = {
                "messaging.system": self._system,
                "messaging.operation.name": "process",
            }
            if topic:
                attributes["messaging.destination.name"] = topic

            start = time.perf_counter()
            try:
                result = await handler(msg)
                self._consumed_messages.add(1, attributes)
                return result
            except Exception as e:
                attributes["error.type"] = type(e).__name__
                raise
            finally:
                duration = time.perf_counter() - start
                self._process_duration.record(duration, attributes)

        return wrapper


class MetricsPublisher:
    """Publisher wrapper that records metrics for sent messages.

    Tracks:
    - messaging.client.operation.duration: Publish duration histogram
    - messaging.client.sent.messages: Message count

    Example:
        publisher = MetricsPublisher(my_publisher)
        await publisher.publish("topic", message)
    """

    def __init__(
        self,
        publisher: Publisher,
        meter_provider: MeterProvider | None = None,
        messaging_system: str = "natricine",
    ) -> None:
        self._publisher = publisher
        provider = meter_provider or metrics.get_meter_provider()
        meter = provider.get_meter("natricine.otel")

        self._operation_duration = meter.create_histogram(
            "messaging.client.operation.duration",
            unit="s",
            description="Duration of messaging operation",
        )
        self._sent_messages = meter.create_counter(
            "messaging.client.sent.messages",
            unit="{message}",
            description="Number of messages producer attempted to send",
        )
        self._system = messaging_system

    async def publish(self, topic: str, *messages: Message) -> None:
        """Publish messages with metrics."""
        attributes: dict[str, Any] = {
            "messaging.system": self._system,
            "messaging.operation.name": "send",
            "messaging.destination.name": topic,
        }

        start = time.perf_counter()
        try:
            traced_messages = tuple(inject_context(msg) for msg in messages)
            await self._publisher.publish(topic, *traced_messages)
            self._sent_messages.add(len(traced_messages), attributes)
        except Exception as e:
            attributes["error.type"] = type(e).__name__
            raise
        finally:
            duration = time.perf_counter() - start
            self._operation_duration.record(duration, attributes)

    async def close(self) -> None:
        """Close the underlying publisher."""
        await self._publisher.close()

    async def __aenter__(self) -> "MetricsPublisher":
        await self._publisher.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        await self._publisher.__aexit__(exc_type, exc_val, exc_tb)
