# natricine-otel

OpenTelemetry instrumentation for natricine.

## Installation

```bash
pip install natricine-otel
```

## Tracing

### Middleware (Consumer Spans)

```python
from natricine.router import Router
from natricine.otel import tracing

router = Router()
router.add_middleware(tracing())

# Each message handler creates a CONSUMER span with:
# - messaging.system: "natricine"
# - messaging.operation.type: "process"
# - messaging.destination.name: topic
# - messaging.message.id: message UUID
```

### Publisher (Producer Spans)

```python
from natricine.otel import TracingPublisher

publisher = TracingPublisher(my_publisher)

# Each publish creates a PRODUCER span and injects trace context
await publisher.publish("orders", message)
```

### Context Propagation

Trace context is automatically propagated via W3C `traceparent` in message metadata:

```python
from natricine.otel import inject_context, extract_context

# Manual injection (TracingPublisher does this automatically)
message = inject_context(message)

# Manual extraction
ctx = extract_context(message)
```

## Metrics

### Middleware (Consumer Metrics)

```python
from natricine.otel import metrics_middleware

router.add_middleware(metrics_middleware())

# Records:
# - messaging.process.duration (histogram)
# - messaging.client.consumed.messages (counter)
```

### Publisher (Producer Metrics)

```python
from natricine.otel import MetricsPublisher

publisher = MetricsPublisher(my_publisher)

# Records:
# - messaging.client.operation.duration (histogram)
# - messaging.client.sent.messages (counter)
```

## Full Example

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

from natricine.router import Router
from natricine.otel import tracing, metrics_middleware, TracingPublisher

# Set up OTEL
provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)

# Instrument natricine
router = Router()
router.add_middleware(tracing())
router.add_middleware(metrics_middleware())

publisher = TracingPublisher(my_publisher)
```

## Custom Configuration

```python
tracing(
    tracer_provider=my_provider,      # Custom provider (default: global)
    messaging_system="my-system",      # messaging.system attribute
    topic_from_metadata="topic",       # Extract topic from message metadata
)

TracingMiddleware(
    tracer_provider=my_provider,
    topic_extractor=lambda msg: msg.metadata.get("topic"),
)
```
