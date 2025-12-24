"""HTTP Subscriber implementation."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from types import TracebackType

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from natricine.pubsub import Message
from natricine_http.config import HTTPSubscriberConfig
from natricine_http.marshaling import extract_metadata, extract_uuid


@dataclass
class _PendingMessage:
    """Internal wrapper for messages awaiting ack/nack."""

    message: Message
    result: asyncio.Event = field(default_factory=asyncio.Event)
    acked: bool = False


class HTTPSubscriber:
    """Subscriber that receives webhooks via HTTP POST requests.

    Provides a Starlette ASGI app that can be mounted in FastAPI/Starlette.
    Incoming POST requests to /{topic} are converted to Messages.

    The HTTP response is held until ack() or nack() is called:
    - ack() returns HTTP 200
    - nack() returns HTTP 500

    Compatible with watermill-http default format.

    Example:
        from fastapi import FastAPI
        from natricine_http import HTTPSubscriber

        app = FastAPI()
        subscriber = HTTPSubscriber()
        app.mount("/webhooks", subscriber.app)

        async for msg in subscriber.subscribe("orders"):
            process(msg)
            await msg.ack()  # Returns 200 to webhook sender
    """

    def __init__(self, config: HTTPSubscriberConfig | None = None) -> None:
        self._config = config or HTTPSubscriberConfig()
        self._queues: dict[str, asyncio.Queue[_PendingMessage]] = {}
        self._closed = False
        self._app = Starlette(
            routes=[
                Route("/{topic:path}", self._handle_request, methods=["POST"]),
            ],
        )

    @property
    def app(self) -> Starlette:
        """ASGI app to mount in FastAPI/Starlette."""
        return self._app

    def _get_queue(self, topic: str) -> asyncio.Queue[_PendingMessage]:
        if topic not in self._queues:
            self._queues[topic] = asyncio.Queue()
        return self._queues[topic]

    async def _handle_request(self, request: Request) -> Response:
        """Handle incoming webhook POST request."""
        topic = request.path_params["topic"]
        payload = await request.body()
        headers = dict(request.headers)

        # Create message with metadata from headers
        message = Message(
            payload=payload,
            metadata=extract_metadata(headers, self._config.metadata_header),
            uuid=extract_uuid(headers, self._config.uuid_header),
        )

        pending = _PendingMessage(message=message)

        # Create ack/nack closures that signal completion
        async def ack() -> None:
            pending.acked = True
            pending.result.set()

        async def nack() -> None:
            pending.acked = False
            pending.result.set()

        # Inject ack/nack into message
        message._ack_func = ack
        message._nack_func = nack

        # Enqueue for subscriber
        queue = self._get_queue(topic)
        await queue.put(pending)

        # Wait for processing to complete
        await pending.result.wait()

        if pending.acked:
            return Response(status_code=200, content="OK")
        else:
            return Response(status_code=500, content="Processing failed")

    def subscribe(self, topic: str) -> AsyncIterator[Message]:
        """Subscribe to messages on a topic.

        Returns an async iterator that yields Messages as they arrive.
        """
        return self._subscribe_iter(topic)

    async def _subscribe_iter(self, topic: str) -> AsyncIterator[Message]:
        queue = self._get_queue(topic)
        while not self._closed:
            try:
                pending = await asyncio.wait_for(queue.get(), timeout=1.0)
                yield pending.message
            except asyncio.TimeoutError:
                continue

    async def close(self) -> None:
        """Close the subscriber."""
        self._closed = True

    async def __aenter__(self) -> "HTTPSubscriber":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()
