"""EventBus - dispatches events to multiple handlers."""

import inspect
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, get_type_hints

import anyio

from natricine_cqrs.depends import call_with_deps
from natricine_cqrs.marshaler import Marshaler
from natricine_pubsub import Message, Publisher, Subscriber

E = TypeVar("E")

EventHandler = Callable[..., Awaitable[None]]


class EventBus:
    """Dispatches events to their handlers.

    Each event type can have multiple handlers.
    """

    def __init__(
        self,
        publisher: Publisher,
        subscriber: Subscriber,
        marshaler: Marshaler,
        topic_prefix: str = "event.",
    ) -> None:
        self._publisher = publisher
        self._subscriber = subscriber
        self._marshaler = marshaler
        self._topic_prefix = topic_prefix
        self._handlers: dict[type, list[EventHandler]] = {}
        self._running = False
        self._cancel_scope: anyio.CancelScope | None = None

    def handler(self, func: EventHandler) -> EventHandler:
        """Decorator to register an event handler.

        The event type is inferred from the first parameter's type hint.
        Multiple handlers can be registered for the same event type.

        Usage:
            @event_bus.handler
            async def on_user_created(event: UserCreated) -> None:
                ...
        """
        hints = get_type_hints(func)
        params = list(inspect.signature(func).parameters.keys())

        if not params:
            msg = f"Handler {func.__name__} must have at least one parameter"
            raise TypeError(msg)

        first_param = params[0]
        if first_param not in hints:
            msg = f"First parameter '{first_param}' of {func.__name__} must be typed"
            raise TypeError(msg)

        event_type = hints[first_param]
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(func)
        return func

    async def publish(self, event: Any) -> None:
        """Publish an event to all registered handlers."""
        event_type = type(event)
        topic = self._topic_prefix + self._marshaler.name(event_type)
        payload = self._marshaler.marshal(event)
        await self._publisher.publish(topic, Message(payload=payload))

    async def run(self) -> None:
        """Run the event bus, processing events until closed."""
        if self._running:
            msg = "EventBus is already running"
            raise RuntimeError(msg)

        self._running = True
        try:
            async with anyio.create_task_group() as tg:
                self._cancel_scope = tg.cancel_scope
                # Each handler gets its own subscription
                for event_type, handlers in self._handlers.items():
                    topic = self._topic_prefix + self._marshaler.name(event_type)
                    for handler in handlers:
                        tg.start_soon(self._run_handler, topic, event_type, handler)
        finally:
            self._running = False
            self._cancel_scope = None

    async def _run_handler(
        self,
        topic: str,
        event_type: type,
        handler: EventHandler,
    ) -> None:
        """Process events for a single handler."""
        async for msg in self._subscriber.subscribe(topic):
            try:
                event = self._marshaler.unmarshal(msg.payload, event_type)
                await call_with_deps(handler, {_first_param_name(handler): event})
                await msg.ack()
            except Exception:
                await msg.nack()
                raise

    async def close(self) -> None:
        """Stop the event bus."""
        if self._cancel_scope:
            self._cancel_scope.cancel()


def _first_param_name(func: Callable[..., Any]) -> str:
    """Get the name of the first parameter of a function."""
    return next(iter(inspect.signature(func).parameters.keys()))
