"""CommandBus - dispatches commands to their single handler."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, ParamSpec, get_type_hints, overload

import anyio

from natricine.cqrs.depends import call_with_deps
from natricine.cqrs.marshaler import Marshaler
from natricine.pubsub import Message, Publisher, Subscriber

if TYPE_CHECKING:
    from natricine.cqrs.router import CommandRouter

P = ParamSpec("P")

# Type alias for handlers that can be sync or async
Handler = Callable[..., None] | Callable[..., Awaitable[None]]


class CommandBus:
    """Dispatches commands to their handlers.

    Each command type has exactly one handler.
    """

    def __init__(
        self,
        publisher: Publisher,
        subscriber: Subscriber,
        marshaler: Marshaler,
        topic_prefix: str = "command.",
        close_timeout_s: float = 30.0,
    ) -> None:
        self._publisher = publisher
        self._subscriber = subscriber
        self._marshaler = marshaler
        self._topic_prefix = topic_prefix
        self._close_timeout_s = close_timeout_s
        self._handlers: dict[type, Handler] = {}
        self._handler_prefixes: dict[type, str] = {}
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
        """Decorator to register a command handler.

        The command type is inferred from the first parameter's type hint.
        Supports both sync and async handlers.

        Usage:
            @command_bus.handler
            async def handle_create_user(cmd: CreateUser) -> None:
                ...

            @command_bus.handler
            def handle_delete_user(cmd: DeleteUser) -> None:
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

        command_type = hints[first_param]
        self._handlers[command_type] = func
        return func

    def include_router(
        self,
        router: "CommandRouter",
        prefix: str = "",
    ) -> None:
        """Include handlers from a CommandRouter.

        Args:
            router: CommandRouter with handlers to include.
            prefix: Optional prefix to prepend to topic names for these handlers.

        Raises:
            ValueError: If a command type already has a handler registered.
        """
        for command_type, handler in router._handlers.items():
            if command_type in self._handlers:
                msg = f"Handler already registered for {command_type.__name__}"
                raise ValueError(msg)
            self._handlers[command_type] = handler
            if prefix:
                self._handler_prefixes[command_type] = prefix

    def _topic_for_type(self, command_type: type) -> str:
        """Get the topic name for a command type."""
        extra_prefix = self._handler_prefixes.get(command_type, "")
        return self._topic_prefix + extra_prefix + self._marshaler.name(command_type)

    async def send(self, command: Any) -> None:
        """Send a command to be handled."""
        command_type = type(command)
        topic = self._topic_for_type(command_type)
        payload = self._marshaler.marshal(command)
        await self._publisher.publish(topic, Message(payload=payload))

    @property
    def in_flight(self) -> int:
        """Number of commands currently being processed."""
        return self._in_flight

    @property
    def is_closing(self) -> bool:
        """Whether the bus is in the process of closing."""
        return self._closing

    async def run(self) -> None:
        """Run the command bus, processing commands until closed."""
        if self._running:
            msg = "CommandBus is already running"
            raise RuntimeError(msg)

        self._running = True
        self._closing = False
        try:
            async with anyio.create_task_group() as tg:
                self._cancel_scope = tg.cancel_scope
                for command_type, handler in self._handlers.items():
                    topic = self._topic_for_type(command_type)
                    tg.start_soon(self._run_handler, topic, command_type, handler)
        finally:
            self._running = False
            self._closing = False
            self._cancel_scope = None

    async def _run_handler(
        self,
        topic: str,
        command_type: type,
        handler: Handler,
    ) -> None:
        """Process commands for a single handler."""
        async for msg in self._subscriber.subscribe(topic):
            # Stop processing new messages if closing
            if self._closing:
                await msg.nack()
                break

            self._in_flight += 1
            try:
                command = self._marshaler.unmarshal(msg.payload, command_type)
                await call_with_deps(handler, {_first_param_name(handler): command})
                await msg.ack()
            except Exception:
                await msg.nack()
                raise
            finally:
                self._in_flight -= 1

    async def close(self) -> None:
        """Stop the command bus gracefully.

        Stops accepting new commands and waits for in-flight commands to complete.
        If in-flight commands don't complete within timeout, forces cancellation.
        """
        if not self._running:
            return

        self._closing = True

        # Wait for in-flight commands to complete (with timeout)
        with anyio.move_on_after(self._close_timeout_s):
            while self._in_flight > 0:
                await anyio.sleep(0.05)

        # Force cancel if still running
        if self._cancel_scope:
            self._cancel_scope.cancel()


def _first_param_name(func: Callable[..., Any]) -> str:
    """Get the name of the first parameter of a function."""
    return next(iter(inspect.signature(func).parameters.keys()))
