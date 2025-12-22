"""FastAPI dependencies for the chat application."""

from chat_example.store import ChatStore
from natricine.cqrs import CommandBus, EventBus, PydanticMarshaler
from natricine.pubsub import InMemoryPubSub

# Shared instances
_pubsub = InMemoryPubSub()
_marshaler = PydanticMarshaler()
_chat_store = ChatStore()

# Buses
_command_bus = CommandBus(_pubsub, _pubsub, _marshaler)
_event_bus = EventBus(_pubsub, _pubsub, _marshaler)


def get_pubsub() -> InMemoryPubSub:
    """Get the shared pubsub instance."""
    return _pubsub


def get_chat_store() -> ChatStore:
    """Get the shared chat store instance."""
    return _chat_store


def get_command_bus() -> CommandBus:
    """Get the shared command bus instance."""
    return _command_bus


def get_event_bus() -> EventBus:
    """Get the shared event bus instance."""
    return _event_bus
