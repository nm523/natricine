"""EventBus - dispatches events to multiple handlers."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, ParamSpec, Protocol, get_type_hints, overload

import anyio

from natricine.cqrs.depends import call_with_deps
from natricine.cqrs.marshaler import Marshaler
from natricine.pubsub import Message, Publisher, Subscriber

if TYPE_CHECKING:
    from natricine.cqrs.router import EventRouter

P = ParamSpec("P")

# Type alias for handlers that can be sync or async
Handler = Callable[..., None] | Callable[..., Awaitable[None]]

# Topic generation callback - receives event name (str), returns topic (str)
GenerateTopicFn = Callable[[str], str]


class SubscriberFactory(Protocol):
    """Factory that creates a Subscriber for each handler.

    Used for fan-out patterns where each handler needs its own subscription
    (e.g., separate SQS queues per handler for SNS fan-out).
    """

    def __call__(self, handler_name: str) -> Subscriber:
        """Create a subscriber for the given handler.

        Args:
            handler_name: Name of the handler function.

        Returns:
            A Subscriber instance configured for this handler.
        """
        ...


class EventBus:
    """Dispatches events to their handlers.

    Each event type can have multiple handlers.

    Args:
        publisher: Publisher for sending events.
        subscriber: Shared subscriber for all handlers. Either this or
            subscriber_factory must be provided.
        marshaler: Marshaler for serializing/deserializing events.
        subscriber_factory: Factory that creates a subscriber per handler.
            Use this for fan-out patterns (e.g., SNS→SQS where each handler
            needs its own queue). Either this or subscriber must be provided.
        generate_topic: Custom topic generation function. Receives event name,
            returns topic string. If not provided, uses topic_prefix + event_name.
        topic_prefix: Prefix for auto-generated topic names (default: "event.").
        close_timeout_s: Timeout for graceful shutdown.
    """

    def __init__(
        self,
        publisher: Publisher,
        subscriber: Subscriber | None = None,
        marshaler: Marshaler | None = None,
        *,
        subscriber_factory: SubscriberFactory | None = None,
        generate_topic: GenerateTopicFn | None = None,
        topic_prefix: str = "event.",
        close_timeout_s: float = 30.0,
    ) -> None:
        if subscriber is None and subscriber_factory is None:
            msg = "Must provide either subscriber or subscriber_factory"
            raise ValueError(msg)
        if marshaler is None:
            msg = "marshaler is required"
            raise ValueError(msg)

        self._publisher = publisher
        self._subscriber = subscriber
        self._subscriber_factory = subscriber_factory
        self._marshaler = marshaler
        self._generate_topic = generate_topic
        self._topic_prefix = topic_prefix
        self._close_timeout_s = close_timeout_s
        self._handlers: dict[type, list[Handler]] = {}
        self._handler_prefixes: dict[type, str] = {}
        self._handler_subscribers: dict[str, Subscriber] = {}  # For factory-created
        self._running = False
        self._closing = False
        self._in_flight = 0
        self._cancel_scope: anyio.CancelScope | None = None

    @overload
    def handler(
        self, func: Callable[P, Awaitable[None]]
    ) -> Callable[P, Awaitable[None]]: ...

    @overload
    def handler(self, func: Callable[P, None]) -> Callable[P, None]: ...

    def handler(
        self, func: Callable[P, Awaitable[None]] | Callable[P, None]
    ) -> Callable[P, Awaitable[None]] | Callable[P, None]:
        """Decorator to register an event handler.

        The event type is inferred from the first parameter's type hint.
        Multiple handlers can be registered for the same event type.
        Supports both sync and async handlers.

        Usage:
            @event_bus.handler
            async def on_user_created(event: UserCreated) -> None:
                ...

            @event_bus.handler
            def on_user_deleted(event: UserDeleted) -> None:
                ...
        """
        hints = get_type_hints(func)
        params = list(inspect.signature(func).parameters.keys())

        func_name = getattr(func, "__name__", repr(func))

        if not params:
            msg = f"Handler {func_name} must have at least one parameter"
            raise TypeError(msg)

        first_param = params[0]
        if first_param not in hints:
            msg = f"First parameter '{first_param}' of {func_name} must be typed"
            raise TypeError(msg)

        event_type = hints[first_param]
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(func)
        return func

    def include_router(
        self,
        router: EventRouter,
        prefix: str = "",
    ) -> None:
        """Include handlers from an EventRouter.

        Args:
            router: EventRouter with handlers to include.
            prefix: Optional prefix to prepend to topic names for these handlers.
        """
        for event_type, handlers in router._handlers.items():
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            self._handlers[event_type].extend(handlers)
            if prefix and event_type not in self._handler_prefixes:
                self._handler_prefixes[event_type] = prefix

    def _topic_for_type(self, event_type: type) -> str:
        """Get the topic name for an event type."""
        event_name = self._marshaler.name(event_type)
        if self._generate_topic is not None:
            return self._generate_topic(event_name)
        # Default: prefix + optional handler prefix + event name
        extra_prefix = self._handler_prefixes.get(event_type, "")
        return self._topic_prefix + extra_prefix + event_name

    async def publish(self, event: Any) -> None:
        """Publish an event to all registered handlers."""
        event_type = type(event)
        topic = self._topic_for_type(event_type)
        payload = self._marshaler.marshal(event)
        await self._publisher.publish(topic, Message(payload=payload))

    @property
    def in_flight(self) -> int:
        """Number of events currently being processed."""
        return self._in_flight

    @property
    def is_closing(self) -> bool:
        """Whether the bus is in the process of closing."""
        return self._closing

    async def run(self) -> None:
        """Run the event bus, processing events until closed."""
        if self._running:
            msg = "EventBus is already running"
            raise RuntimeError(msg)

        self._running = True
        self._closing = False
        try:
            async with anyio.create_task_group() as tg:
                self._cancel_scope = tg.cancel_scope
                # Each handler gets its own subscription
                for event_type, handlers in self._handlers.items():
                    topic = self._topic_for_type(event_type)
                    for handler in handlers:
                        tg.start_soon(self._run_handler, topic, event_type, handler)
        finally:
            self._running = False
            self._closing = False
            self._cancel_scope = None

    def _get_subscriber_for_handler(self, handler: Handler) -> Subscriber:
        """Get or create subscriber for a handler.

        If subscriber_factory is set, creates a subscriber per handler.
        Otherwise, uses the shared subscriber.
        """
        if self._subscriber_factory is not None:
            handler_name = getattr(handler, "__name__", repr(handler))
            if handler_name not in self._handler_subscribers:
                self._handler_subscribers[handler_name] = self._subscriber_factory(
                    handler_name
                )
            return self._handler_subscribers[handler_name]
        # subscriber is guaranteed non-None if factory is None (checked in __init__)
        assert self._subscriber is not None
        return self._subscriber

    async def _run_handler(
        self,
        topic: str,
        event_type: type,
        handler: Handler,
    ) -> None:
        """Process events for a single handler."""
        subscriber = self._get_subscriber_for_handler(handler)
        async for msg in subscriber.subscribe(topic):
            # Stop processing new messages if closing
            if self._closing:
                await msg.nack()
                break

            self._in_flight += 1
            try:
                event = self._marshaler.unmarshal(msg.payload, event_type)
                await call_with_deps(handler, {_first_param_name(handler): event})
                await msg.ack()
            except Exception:
                await msg.nack()
                raise
            finally:
                self._in_flight -= 1

    async def close(self) -> None:
        """Stop the event bus gracefully.

        Stops accepting new events and waits for in-flight events to complete.
        If in-flight events don't complete within close_timeout_s, forces cancellation.
        Also closes any factory-created subscribers.
        """
        if not self._running:
            return

        self._closing = True

        # Wait for in-flight events to complete (with timeout)
        with anyio.move_on_after(self._close_timeout_s):
            while self._in_flight > 0:
                await anyio.sleep(0.05)

        # Force cancel if still running
        if self._cancel_scope:
            self._cancel_scope.cancel()

        # Close factory-created subscribers
        for subscriber in self._handler_subscribers.values():
            if hasattr(subscriber, "close"):
                await subscriber.close()
        self._handler_subscribers.clear()


def _first_param_name(func: Callable[..., Any]) -> str:
    """Get the name of the first parameter of a function."""
    return next(iter(inspect.signature(func).parameters.keys()))
