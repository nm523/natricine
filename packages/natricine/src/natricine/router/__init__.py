"""natricine-router: Message routing layer."""

from natricine.router.middleware import (
    POISON_HANDLER_KEY,
    POISON_REASON_KEY,
    POISON_SUBSCRIBER_KEY,
    POISON_TOPIC_KEY,
    PermanentError,
    dead_letter_queue,
    poison_queue,
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
    "POISON_HANDLER_KEY",
    "POISON_REASON_KEY",
    "POISON_SUBSCRIBER_KEY",
    "POISON_TOPIC_KEY",
    "PermanentError",
    "Router",
    "RouterConfig",
    "dead_letter_queue",
    "graceful_shutdown",
    "poison_queue",
    "recoverer",
    "retry",
    "timeout",
]
