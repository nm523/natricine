"""Router - orchestrates message flow through handlers."""

from dataclasses import dataclass

import anyio
from anyio import CancelScope

from natricine.pubsub import Message, Publisher, Subscriber
from natricine.router.handler import Handler
from natricine.router.types import HandlerFunc, Middleware, NoPublishHandlerFunc


@dataclass
class RouterConfig:
    """Router configuration."""

    close_timeout_s: float = 30.0


class Router:
    """Routes messages between subscribers and publishers through handlers."""

    def __init__(self, config: RouterConfig | None = None) -> None:
        self._config = config or RouterConfig()
        self._handlers: list[Handler] = []
        self._middlewares: list[Middleware] = []
        self._running = False
        self._closing = False
        self._in_flight = 0
        self._cancel_scope: CancelScope | None = None

    def add_middleware(self, middleware: Middleware) -> None:
        """Add router-level middleware (applies to all handlers)."""
        self._middlewares.append(middleware)

    def add_handler(
        self,
        name: str,
        subscribe_topic: str,
        subscriber: Subscriber,
        publish_topic: str,
        publisher: Publisher,
        handler_func: HandlerFunc,
        middlewares: list[Middleware] | None = None,
    ) -> None:
        """Add a handler that may publish output messages."""
        self._handlers.append(
            Handler(
                name=name,
                subscriber=subscriber,
                subscribe_topic=subscribe_topic,
                handler_func=handler_func,
                publisher=publisher,
                publish_topic=publish_topic,
                middlewares=middlewares or [],
            )
        )

    def add_no_publisher_handler(
        self,
        name: str,
        subscribe_topic: str,
        subscriber: Subscriber,
        handler_func: NoPublishHandlerFunc,
        middlewares: list[Middleware] | None = None,
    ) -> None:
        """Add a handler that only consumes messages (no output)."""

        async def wrapped(msg: Message) -> list[Message] | None:
            await handler_func(msg)
            return None

        self._handlers.append(
            Handler(
                name=name,
                subscriber=subscriber,
                subscribe_topic=subscribe_topic,
                handler_func=wrapped,
                middlewares=middlewares or [],
            )
        )

    async def run(self) -> None:
        """Run the router, processing messages until closed."""
        if self._running:
            msg = "Router is already running"
            raise RuntimeError(msg)

        self._running = True
        self._closing = False
        try:
            async with anyio.create_task_group() as tg:
                self._cancel_scope = tg.cancel_scope
                for handler in self._handlers:
                    tg.start_soon(self._run_handler, handler)
        finally:
            self._running = False
            self._closing = False
            self._cancel_scope = None

    @property
    def in_flight(self) -> int:
        """Number of messages currently being processed."""
        return self._in_flight

    @property
    def is_closing(self) -> bool:
        """Whether the router is in the process of closing."""
        return self._closing

    async def close(self) -> None:
        """Stop the router gracefully.

        Stops accepting new messages and waits for in-flight messages to complete.
        If in-flight messages don't complete within timeout, forces cancellation.
        """
        if not self._running:
            return

        self._closing = True

        # Wait for in-flight messages to complete (with timeout)
        with anyio.move_on_after(self._config.close_timeout_s):
            while self._in_flight > 0:
                await anyio.sleep(0.05)

        # Force cancel if still running
        if self._cancel_scope:
            self._cancel_scope.cancel()

    async def _run_handler(self, handler: Handler) -> None:
        """Run a single handler, processing messages from its subscriber."""
        # Build middleware chain: router middlewares + handler middlewares
        wrapped_func = handler.handler_func
        for middleware in reversed(handler.middlewares):
            wrapped_func = middleware(wrapped_func)
        for middleware in reversed(self._middlewares):
            wrapped_func = middleware(wrapped_func)

        async for msg in handler.subscriber.subscribe(handler.subscribe_topic):
            # Stop processing new messages if closing
            if self._closing:
                await msg.nack()
                break

            self._in_flight += 1
            try:
                output_messages = await wrapped_func(msg)
                await msg.ack()

                if output_messages and handler.publisher and handler.publish_topic:
                    await handler.publisher.publish(
                        handler.publish_topic, *output_messages
                    )
            except Exception:
                await msg.nack()
                raise
            finally:
                self._in_flight -= 1

    async def __aenter__(self) -> "Router":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        await self.close()
