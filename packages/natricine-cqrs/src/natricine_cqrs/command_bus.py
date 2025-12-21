"""CommandBus - dispatches commands to their single handler."""

import inspect
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, get_type_hints

import anyio

from natricine_cqrs.depends import call_with_deps
from natricine_cqrs.marshaler import Marshaler
from natricine_pubsub import Message, Publisher, Subscriber

C = TypeVar("C")

CommandHandler = Callable[..., Awaitable[None]]


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
    ) -> None:
        self._publisher = publisher
        self._subscriber = subscriber
        self._marshaler = marshaler
        self._topic_prefix = topic_prefix
        self._handlers: dict[type, CommandHandler] = {}
        self._running = False
        self._cancel_scope: anyio.CancelScope | None = None

    def handler(self, func: CommandHandler) -> CommandHandler:
        """Decorator to register a command handler.

        The command type is inferred from the first parameter's type hint.

        Usage:
            @command_bus.handler
            async def handle_create_user(cmd: CreateUser) -> None:
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

        command_type = hints[first_param]
        self._handlers[command_type] = func
        return func

    async def send(self, command: Any) -> None:
        """Send a command to be handled."""
        command_type = type(command)
        topic = self._topic_prefix + self._marshaler.name(command_type)
        payload = self._marshaler.marshal(command)
        await self._publisher.publish(topic, Message(payload=payload))

    async def run(self) -> None:
        """Run the command bus, processing commands until closed."""
        if self._running:
            msg = "CommandBus is already running"
            raise RuntimeError(msg)

        self._running = True
        try:
            async with anyio.create_task_group() as tg:
                self._cancel_scope = tg.cancel_scope
                for command_type, handler in self._handlers.items():
                    topic = self._topic_prefix + self._marshaler.name(command_type)
                    tg.start_soon(self._run_handler, topic, command_type, handler)
        finally:
            self._running = False
            self._cancel_scope = None

    async def _run_handler(
        self,
        topic: str,
        command_type: type,
        handler: CommandHandler,
    ) -> None:
        """Process commands for a single handler."""
        async for msg in self._subscriber.subscribe(topic):
            try:
                command = self._marshaler.unmarshal(msg.payload, command_type)
                await call_with_deps(handler, {_first_param_name(handler): command})
                await msg.ack()
            except Exception:
                await msg.nack()
                raise

    async def close(self) -> None:
        """Stop the command bus."""
        if self._cancel_scope:
            self._cancel_scope.cancel()


def _first_param_name(func: Callable[..., Any]) -> str:
    """Get the name of the first parameter of a function."""
    return next(iter(inspect.signature(func).parameters.keys()))
