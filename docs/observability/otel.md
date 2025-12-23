# OpenTelemetry

Distributed tracing and metrics for natricine using OpenTelemetry.

## Installation

```bash
pip install natricine-otel
```

## Tracing Middleware

Add tracing to message handlers with the `tracing` middleware:

```python
from natricine.router import Router
from natricine.otel import tracing

router = Router(subscriber)

# Add tracing middleware
router.add_middleware(tracing())

@router.handler("orders")
async def handle_order(msg: Message) -> None:
    # Spans are automatically created for each message
    await process_order(msg)
```

### Configuration

```python
router.add_middleware(tracing(
    tracer_provider=my_tracer_provider,  # Custom TracerProvider (uses global if not set)
    messaging_system="natricine",        # messaging.system attribute value
    topic_from_metadata="topic",         # Metadata key containing topic name
))
```

### Span Attributes

Each span includes:

| Attribute | Value |
|-----------|-------|
| `messaging.system` | Configurable (default: "natricine") |
| `messaging.operation.type` | "process" |
| `messaging.operation.name` | "process" |
| `messaging.message.id` | Message UUID |
| `messaging.destination.name` | Topic name (if configured) |
| `error.type` | Exception class name (on failure) |

## Tracing Publisher

Wrap publishers to inject trace context into messages:

```python
from natricine.otel import TracingPublisher

publisher = TracingPublisher(my_publisher)

# Trace context is automatically injected into message metadata
await publisher.publish("orders", Message(payload=b"data"))
```

This enables distributed tracing across service boundaries.

## Metrics Middleware

Add metrics collection to handlers:

```python
from natricine.otel import metrics_middleware

router.add_middleware(metrics_middleware())
```

### Recorded Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `messaging.process.duration` | Histogram | Processing time in seconds |
| `messaging.client.consumed.messages` | Counter | Messages processed |

### Configuration

```python
router.add_middleware(metrics_middleware(
    meter_provider=my_meter_provider,    # Custom MeterProvider
    messaging_system="natricine",        # messaging.system attribute
    topic_from_metadata="topic",         # Metadata key for topic name
))
```

## Metrics Publisher

Wrap publishers to record send metrics:

```python
from natricine.otel import MetricsPublisher

publisher = MetricsPublisher(my_publisher)
await publisher.publish("orders", Message(payload=b"data"))
```

### Recorded Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `messaging.client.operation.duration` | Histogram | Publish time in seconds |
| `messaging.client.sent.messages` | Counter | Messages sent |

## Class-Based Middleware

For more control, use the class-based versions:

```python
from natricine.otel import TracingMiddleware, MetricsMiddleware

# Custom topic extractor
tracing_mw = TracingMiddleware(
    topic_extractor=lambda msg: msg.metadata.get("topic")
)

metrics_mw = MetricsMiddleware(
    topic_extractor=lambda msg: msg.metadata.get("topic")
)

router.add_middleware(tracing_mw)
router.add_middleware(metrics_mw)
```

## Context Propagation

Trace context is propagated through message metadata using W3C Trace Context format:

```python
from natricine.otel import inject_context, extract_context

# Inject current span context into message
msg = inject_context(Message(payload=b"data"))
# msg.metadata now contains traceparent, tracestate

# Extract context on receiving end
parent_context = extract_context(msg)
```

## Full Example

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

from natricine.router import Router
from natricine.otel import tracing, metrics_middleware, TracingPublisher, MetricsPublisher

# Set up OpenTelemetry
provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)

# Wrap publisher with tracing and metrics
publisher = TracingPublisher(MetricsPublisher(base_publisher))

# Add middleware to router
router = Router(subscriber)
router.add_middleware(tracing())
router.add_middleware(metrics_middleware())

@router.handler("orders")
async def handle_order(msg: Message) -> None:
    # Traced and measured automatically
    await process_order(msg)

await router.run()
```

## Semantic Conventions

natricine follows [OpenTelemetry Semantic Conventions for Messaging](https://opentelemetry.io/docs/specs/semconv/messaging/).
