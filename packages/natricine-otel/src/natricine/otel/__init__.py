"""OpenTelemetry instrumentation for natricine."""

from natricine.otel.metrics import (
    MetricsMiddleware,
    MetricsPublisher,
    metrics_middleware,
)
from natricine.otel.middleware import TracingMiddleware, tracing
from natricine.otel.propagation import extract_context, inject_context
from natricine.otel.publisher import TracingPublisher

__all__ = [
    "MetricsMiddleware",
    "MetricsPublisher",
    "TracingMiddleware",
    "TracingPublisher",
    "extract_context",
    "inject_context",
    "metrics_middleware",
    "tracing",
]
