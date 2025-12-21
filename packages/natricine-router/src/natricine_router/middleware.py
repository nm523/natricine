"""Built-in middlewares."""

import logging

import anyio

from natricine_pubsub import Message
from natricine_router.types import HandlerFunc, Middleware

DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 1.0
DEFAULT_BACKOFF_MULTIPLIER = 2.0


def recoverer(
    logger: logging.Logger | None = None,
) -> Middleware:
    """Middleware that catches exceptions and logs them instead of crashing."""
    log = logger or logging.getLogger("natricine.router")

    def middleware(next_handler: HandlerFunc) -> HandlerFunc:
        async def handler(msg: Message) -> list[Message] | None:
            try:
                return await next_handler(msg)
            except Exception:
                log.exception("Handler failed for message %s", msg.uuid)
                raise

        return handler

    return middleware


def retry(
    max_retries: int = DEFAULT_MAX_RETRIES,
    delay: float = DEFAULT_RETRY_DELAY,
    backoff: float = DEFAULT_BACKOFF_MULTIPLIER,
) -> Middleware:
    """Middleware that retries failed handlers with exponential backoff."""

    def middleware(next_handler: HandlerFunc) -> HandlerFunc:
        async def handler(msg: Message) -> list[Message] | None:
            last_exception: Exception | None = None
            current_delay = delay

            for attempt in range(max_retries + 1):
                try:
                    return await next_handler(msg)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        await anyio.sleep(current_delay)
                        current_delay *= backoff

            if last_exception:
                raise last_exception
            else:
                raise RuntimeError("Failed to process message after retry")

        return handler

    return middleware


def timeout(seconds: float) -> Middleware:
    """Middleware that cancels handler if it takes too long."""

    def middleware(next_handler: HandlerFunc) -> HandlerFunc:
        async def handler(msg: Message) -> list[Message] | None:
            with anyio.fail_after(seconds):
                return await next_handler(msg)

        return handler

    return middleware
