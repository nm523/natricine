"""Type definitions for the router."""

from collections.abc import Awaitable, Callable

from natricine.pubsub import Message

# Handler that may produce output messages
HandlerFunc = Callable[[Message], Awaitable[list[Message] | None]]

# Handler that only consumes (no output)
NoPublishHandlerFunc = Callable[[Message], Awaitable[None]]

# Middleware wraps a handler function
Middleware = Callable[[HandlerFunc], HandlerFunc]
