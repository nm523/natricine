"""Handler configuration."""

from dataclasses import dataclass, field

from natricine.pubsub import Publisher, Subscriber
from natricine.router.types import HandlerFunc, Middleware


@dataclass
class Handler:
    """Configuration for a message handler."""

    name: str
    subscriber: Subscriber
    subscribe_topic: str
    handler_func: HandlerFunc
    publisher: Publisher | None = None
    publish_topic: str | None = None
    middlewares: list[Middleware] = field(default_factory=list)
