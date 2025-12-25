"""natricine-cqrs: CQRS pattern implementation."""

from natricine.cqrs.command_bus import CommandBus
from natricine.cqrs.depends import Depends
from natricine.cqrs.event_bus import (
    EventBus,
    GenerateTopicFn,
    SubscriberFactory,
)
from natricine.cqrs.marshaler import Marshaler, PydanticMarshaler
from natricine.cqrs.router import CommandRouter, EventRouter

__all__ = [
    "CommandBus",
    "CommandRouter",
    "Depends",
    "EventBus",
    "EventRouter",
    "GenerateTopicFn",
    "Marshaler",
    "PydanticMarshaler",
    "SubscriberFactory",
]
