"""natricine-router: Message routing layer."""

from natricine.router.middleware import (
    PermanentError,
    dead_letter_queue,
    recoverer,
    retry,
    timeout,
)
from natricine.router.router import Router, RouterConfig
from natricine.router.shutdown import graceful_shutdown
from natricine.router.types import HandlerFunc, Middleware, NoPublishHandlerFunc

__all__ = [
    "HandlerFunc",
    "Middleware",
    "NoPublishHandlerFunc",
    "PermanentError",
    "Router",
    "RouterConfig",
    "dead_letter_queue",
    "graceful_shutdown",
    "recoverer",
    "retry",
    "timeout",
]
