# Observability

natricine integrates with OpenTelemetry for distributed tracing and metrics.

## Package

```bash
pip install natricine-otel
```

## Features

| Feature | Component | Description |
|---------|-----------|-------------|
| Tracing | `TracingMiddleware` | Spans for message processing |
| Tracing | `TracingPublisher` | Inject trace context into messages |
| Metrics | `MetricsMiddleware` | Processing duration and message counts |
| Metrics | `MetricsPublisher` | Publish duration and message counts |

## Quick Start

```python
from natricine.router import Router
from natricine.otel import tracing, metrics_middleware

router = Router(subscriber)
router.add_middleware(tracing())
router.add_middleware(metrics_middleware())

@router.handler("orders")
async def handle_order(msg: Message) -> None:
    # Automatically traced and measured
    await process_order(msg)
```

See [OpenTelemetry](otel.md) for full documentation.
