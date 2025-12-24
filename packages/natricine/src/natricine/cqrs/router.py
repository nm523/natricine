"""Routers for deferred handler registration."""

import inspect
from collections.abc import Awaitable, Callable
from typing import ParamSpec, get_type_hints, overload

P = ParamSpec("P")

# Type alias for handlers that can be sync or async
Handler = Callable[..., None] | Callable[..., Awaitable[None]]


class CommandRouter:
    """Collects command handlers for later inclusion in a CommandBus.

    Usage:
        # users/handlers.py
        router = CommandRouter()

        @router.handler
        async def handle_create_user(cmd: CreateUser) -> None:
            ...

        # main.py
        bus = CommandBus(publisher, subscriber, marshaler)
        bus.include_router(router, prefix="users.")
    """

    def __init__(self) -> None:
        self._handlers: dict[type, Handler] = {}

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


class EventRouter:
    """Collects event handlers for later inclusion in an EventBus.

    Usage:
        # notifications/handlers.py
        router = EventRouter()

        @router.handler
        async def send_welcome_email(event: UserCreated) -> None:
            ...

        @router.handler
        async def update_analytics(event: UserCreated) -> None:
            ...

        # main.py
        bus = EventBus(publisher, subscriber, marshaler)
        bus.include_router(router, prefix="notifications.")
    """

    def __init__(self) -> None:
        self._handlers: dict[type, list[Handler]] = {}

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
