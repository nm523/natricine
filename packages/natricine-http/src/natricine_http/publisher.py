"""HTTP Publisher implementation."""

from types import TracebackType

import httpx

from natricine.pubsub import Message
from natricine_http.config import HTTPPublisherConfig
from natricine_http.marshaling import metadata_to_header


class HTTPPublisher:
    """Publisher that sends messages as HTTP POST requests.

    Messages are sent to {base_url}/{topic} with:
    - Payload as request body
    - UUID in Message-Uuid header (configurable)
    - Metadata as JSON in Message-Metadata header (configurable)

    Compatible with watermill-http default format.

    Example:
        config = HTTPPublisherConfig(base_url="http://api.example.com")
        async with HTTPPublisher(config) as publisher:
            await publisher.publish("orders", Message(payload=b'{"id": 1}'))
    """

    def __init__(self, config: HTTPPublisherConfig) -> None:
        self._config = config
        self._client: httpx.AsyncClient | None = None
        self._closed = False

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._config.base_url,
                timeout=self._config.timeout_s,
                headers=self._config.headers,
            )
        return self._client

    async def publish(self, topic: str, *messages: Message) -> None:
        """Publish messages to a topic via HTTP POST.

        Each message is sent as a separate HTTP request.
        Raises httpx.HTTPStatusError on non-2xx responses.
        """
        if self._closed:
            msg = "Publisher is closed"
            raise RuntimeError(msg)

        client = await self._get_client()
        url = self._config.topic_path.format(topic=topic)

        for message in messages:
            headers = {
                self._config.uuid_header: str(message.uuid),
                self._config.metadata_header: metadata_to_header(message.metadata),
                "Content-Type": "application/octet-stream",
            }
            response = await client.post(url, content=message.payload, headers=headers)
            response.raise_for_status()

    async def close(self) -> None:
        """Close the HTTP client."""
        self._closed = True
        if self._client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "HTTPPublisher":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()
