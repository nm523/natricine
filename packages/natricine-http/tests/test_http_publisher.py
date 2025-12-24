"""Tests for HTTPPublisher."""

import httpx
import pytest
from natricine_http import HTTPPublisher, HTTPPublisherConfig

from natricine.pubsub import Message


@pytest.mark.anyio
async def test_publish_sends_post_request() -> None:
    """Publisher sends POST request with correct headers."""
    received_requests: list[httpx.Request] = []

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        received_requests.append(request)
        return httpx.Response(200)

    transport = httpx.MockTransport(mock_handler)
    config = HTTPPublisherConfig(base_url="http://test.example.com")
    publisher = HTTPPublisher(config)
    publisher._client = httpx.AsyncClient(
        transport=transport,
        base_url=config.base_url,
    )

    msg = Message(payload=b"test payload", metadata={"key": "value"})
    await publisher.publish("orders", msg)

    assert len(received_requests) == 1
    req = received_requests[0]
    assert req.method == "POST"
    assert str(req.url) == "http://test.example.com/orders"
    assert req.content == b"test payload"
    assert req.headers["X-Natricine-UUID"] == str(msg.uuid)
    assert req.headers["X-Natricine-Meta-key"] == "value"
    assert req.headers["Content-Type"] == "application/octet-stream"

    await publisher.close()


@pytest.mark.anyio
async def test_publish_multiple_messages() -> None:
    """Publisher sends each message as separate request."""
    received_requests: list[httpx.Request] = []

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        received_requests.append(request)
        return httpx.Response(200)

    transport = httpx.MockTransport(mock_handler)
    config = HTTPPublisherConfig(base_url="http://test.example.com")
    publisher = HTTPPublisher(config)
    publisher._client = httpx.AsyncClient(
        transport=transport,
        base_url=config.base_url,
    )

    msg1 = Message(payload=b"first")
    msg2 = Message(payload=b"second")
    await publisher.publish("events", msg1, msg2)

    expected_count = 2
    assert len(received_requests) == expected_count
    assert received_requests[0].content == b"first"
    assert received_requests[1].content == b"second"

    await publisher.close()


@pytest.mark.anyio
async def test_publish_custom_topic_path() -> None:
    """Publisher uses custom topic path pattern."""
    received_requests: list[httpx.Request] = []

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        received_requests.append(request)
        return httpx.Response(200)

    transport = httpx.MockTransport(mock_handler)
    config = HTTPPublisherConfig(
        base_url="http://test.example.com",
        topic_path="/webhooks/{topic}/receive",
    )
    publisher = HTTPPublisher(config)
    publisher._client = httpx.AsyncClient(
        transport=transport,
        base_url=config.base_url,
    )

    await publisher.publish("orders", Message(payload=b"test"))

    req = received_requests[0]
    assert str(req.url) == "http://test.example.com/webhooks/orders/receive"

    await publisher.close()


@pytest.mark.anyio
async def test_publish_raises_on_error_response() -> None:
    """Publisher raises on non-2xx response."""

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Server error")

    transport = httpx.MockTransport(mock_handler)
    config = HTTPPublisherConfig(base_url="http://test.example.com")
    publisher = HTTPPublisher(config)
    publisher._client = httpx.AsyncClient(
        transport=transport,
        base_url=config.base_url,
    )

    with pytest.raises(httpx.HTTPStatusError):
        await publisher.publish("orders", Message(payload=b"test"))

    await publisher.close()


@pytest.mark.anyio
async def test_publish_context_manager() -> None:
    """Publisher works as async context manager."""

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    transport = httpx.MockTransport(mock_handler)
    config = HTTPPublisherConfig(base_url="http://test.example.com")

    async with HTTPPublisher(config) as publisher:
        publisher._client = httpx.AsyncClient(
            transport=transport,
            base_url=config.base_url,
        )
        await publisher.publish("topic", Message(payload=b"test"))

    assert publisher._closed


@pytest.mark.anyio
async def test_publish_after_close_raises() -> None:
    """Publishing after close raises RuntimeError."""
    config = HTTPPublisherConfig(base_url="http://test.example.com")
    publisher = HTTPPublisher(config)
    await publisher.close()

    with pytest.raises(RuntimeError, match="closed"):
        await publisher.publish("topic", Message(payload=b"test"))


@pytest.mark.anyio
async def test_publish_default_headers() -> None:
    """Publisher includes default headers from config."""
    received_requests: list[httpx.Request] = []

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        received_requests.append(request)
        return httpx.Response(200)

    transport = httpx.MockTransport(mock_handler)
    config = HTTPPublisherConfig(
        base_url="http://test.example.com",
        headers={"Authorization": "Bearer token123"},
    )
    publisher = HTTPPublisher(config)
    publisher._client = httpx.AsyncClient(
        transport=transport,
        base_url=config.base_url,
        headers=config.headers,
    )

    await publisher.publish("topic", Message(payload=b"test"))

    req = received_requests[0]
    assert req.headers["Authorization"] == "Bearer token123"

    await publisher.close()
