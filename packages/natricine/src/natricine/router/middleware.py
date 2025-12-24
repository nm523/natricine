"""Built-in middlewares."""

import logging
import random
import traceback as tb
from collections.abc import Callable

import anyio

from natricine.pubsub import Message, Publisher
from natricine.router.types import HandlerFunc, Middleware

DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 1.0
DEFAULT_BACKOFF_MULTIPLIER = 2.0
DEFAULT_JITTER = 0.1


class PermanentError(Exception):
    """Exception that should not be retried.

    Wrap an exception in PermanentError to skip retries and fail immediately.

    Usage:
        raise PermanentError(ValueError("Invalid input - retrying won't help"))
    """

    def __init__(self, cause: Exception) -> None:
        self.cause = cause
        super().__init__(str(cause))


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
    jitter: float = DEFAULT_JITTER,
    retry_on: tuple[type[Exception], ...] | None = None,
    on_retry: Callable[[int, Exception, Message], None] | None = None,
) -> Middleware:
    """Middleware that retries failed handlers with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts (not including initial).
        delay: Initial delay between retries in seconds.
        backoff: Multiplier for delay after each retry.
        jitter: Random jitter factor (0.1 = ±10% randomization).
        retry_on: Tuple of exception types to retry. If None, retries all
            exceptions except PermanentError.
        on_retry: Optional callback called before each retry with
            (attempt_number, exception, message).
    """

    def should_retry(exc: Exception) -> bool:
        if isinstance(exc, PermanentError):
            return False
        if retry_on is None:
            return True
        return isinstance(exc, retry_on)

    def add_jitter(base_delay: float) -> float:
        if jitter <= 0:
            return base_delay
        jitter_range = base_delay * jitter
        return base_delay + random.uniform(-jitter_range, jitter_range)

    def middleware(next_handler: HandlerFunc) -> HandlerFunc:
        async def handler(msg: Message) -> list[Message] | None:
            last_exception: Exception | None = None
            current_delay = delay

            for attempt in range(max_retries + 1):
                try:
                    return await next_handler(msg)
                except Exception as e:
                    # Unwrap PermanentError for the actual exception
                    actual_exception = e.cause if isinstance(e, PermanentError) else e
                    last_exception = actual_exception

                    if not should_retry(e) or attempt >= max_retries:
                        break

                    if on_retry is not None:
                        on_retry(attempt + 1, actual_exception, msg)

                    await anyio.sleep(add_jitter(current_delay))
                    current_delay *= backoff

            if last_exception:
                raise last_exception
            raise RuntimeError("Retry failed unexpectedly")

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


def dead_letter_queue(
    publisher: Publisher,
    topic: str,
    catch: tuple[type[Exception], ...] = (Exception,),
    include_traceback: bool = True,
    on_dlq: Callable[[Message, Exception], None] | None = None,
) -> Middleware:
    """Middleware that sends failed messages to a dead letter queue.

    When an exception occurs (after any retries), the message is published
    to the DLQ topic with error metadata, and processing continues normally
    (the original message will be acked, not nacked).

    Should be placed BEFORE retry middleware in the chain:
        router.add_middleware(dead_letter_queue(pub, "dlq.errors"))
        router.add_middleware(retry(max_retries=3))

    Args:
        publisher: Publisher to send DLQ messages to.
        topic: Topic to publish failed messages to.
        catch: Tuple of exception types to catch and send to DLQ.
            Defaults to all exceptions.
        include_traceback: Whether to include traceback in metadata.
        on_dlq: Optional callback called when a message is sent to DLQ
            with (message, exception).
    """

    def middleware(next_handler: HandlerFunc) -> HandlerFunc:
        async def handler(msg: Message) -> list[Message] | None:
            try:
                return await next_handler(msg)
            except catch as e:
                # Build DLQ metadata
                dlq_metadata = {
                    **msg.metadata,
                    "dlq.error": str(e),
                    "dlq.error_type": type(e).__name__,
                    "dlq.original_uuid": str(msg.uuid),
                }

                if include_traceback:
                    dlq_metadata["dlq.traceback"] = tb.format_exc()

                dlq_msg = Message(
                    payload=msg.payload,
                    metadata=dlq_metadata,
                )

                await publisher.publish(topic, dlq_msg)

                if on_dlq is not None:
                    on_dlq(msg, e)

                # Return normally so the message gets acked
                return None

        return handler

    return middleware
