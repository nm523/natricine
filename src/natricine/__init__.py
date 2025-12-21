"""natricine: Event-driven architecture toolkit for Python.

This is a convenience package that re-exports the core components.
Install specific backends separately (e.g., natricine-redisstream).
"""

from natricine_cqrs import CommandBus, Depends, EventBus, Marshaler, PydanticMarshaler
from natricine_pubsub import InMemoryPubSub, Message, Publisher, Subscriber
from natricine_router import Handler, Middleware, Router

__all__ = [
    # pubsub
    "Message",
    "Publisher",
    "Subscriber",
    "InMemoryPubSub",
    # router
    "Router",
    "Handler",
    "Middleware",
    # cqrs
    "CommandBus",
    "EventBus",
    "Marshaler",
    "PydanticMarshaler",
    "Depends",
]
