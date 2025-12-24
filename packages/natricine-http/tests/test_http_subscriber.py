"""Tests for HTTPSubscriber."""

import asyncio
from http import HTTPStatus
from uuid import UUID

import httpx
import pytest
from natricine_http import HTTPSubscriber


@pytest.mark.anyio
async def test_subscribe_receives_post_request() -> None:
    """Subscriber converts POST requests to Messages."""
    subscriber = HTTPSubscriber()
    received_messages: list[bytes] = []

    async def consume() -> None:
        async for msg in subscriber.subscribe("orders"):
            received_messages.append(msg.payload)
            await msg.ack()
            break

    consumer_task = asyncio.create_task(consume())

    # Give consumer time to start
    await asyncio.sleep(0.1)

    # Send request using httpx async client with ASGI transport
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=subscriber.app),
        base_url="http://test",
    ) as client:
        response = await client.post("/orders", content=b"test payload")
        assert response.status_code == HTTPStatus.OK

    await consumer_task
    await subscriber.close()

    assert received_messages == [b"test payload"]


@pytest.mark.anyio
async def test_subscribe_extracts_metadata() -> None:
    """Subscriber extracts metadata from headers."""
    subscriber = HTTPSubscriber()
    received_metadata: dict[str, str] = {}

    async def consume() -> None:
        async for msg in subscriber.subscribe("events"):
            received_metadata.update(msg.metadata)
            await msg.ack()
            break

    consumer_task = asyncio.create_task(consume())
    await asyncio.sleep(0.1)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=subscriber.app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/events",
            content=b"data",
            headers={
                "X-Natricine-Meta-trace-id": "abc123",
                "X-Natricine-Meta-source": "test",
            },
        )
        assert response.status_code == HTTPStatus.OK

    await consumer_task
    await subscriber.close()

    assert received_metadata["trace-id"] == "abc123"
    assert received_metadata["source"] == "test"


@pytest.mark.anyio
async def test_subscribe_extracts_uuid() -> None:
    """Subscriber extracts UUID from header."""
    subscriber = HTTPSubscriber()
    received_uuid: UUID | None = None

    async def consume() -> None:
        nonlocal received_uuid
        async for msg in subscriber.subscribe("events"):
            received_uuid = msg.uuid
            await msg.ack()
            break

    consumer_task = asyncio.create_task(consume())
    await asyncio.sleep(0.1)

    test_uuid = "12345678-1234-5678-1234-567812345678"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=subscriber.app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/events",
            content=b"data",
            headers={"X-Natricine-UUID": test_uuid},
        )
        assert response.status_code == HTTPStatus.OK

    await consumer_task
    await subscriber.close()

    assert str(received_uuid) == test_uuid


@pytest.mark.anyio
async def test_nack_returns_500() -> None:
    """Nacking a message returns HTTP 500."""
    subscriber = HTTPSubscriber()

    async def consume() -> None:
        async for msg in subscriber.subscribe("orders"):
            await msg.nack()
            break

    consumer_task = asyncio.create_task(consume())
    await asyncio.sleep(0.1)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=subscriber.app),
        base_url="http://test",
    ) as client:
        response = await client.post("/orders", content=b"data")
        assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR

    await consumer_task
    await subscriber.close()


@pytest.mark.anyio
async def test_subscribe_multiple_topics() -> None:
    """Subscriber can handle multiple topics."""
    subscriber = HTTPSubscriber()
    orders_messages: list[bytes] = []
    events_messages: list[bytes] = []

    async def consume_orders() -> None:
        async for msg in subscriber.subscribe("orders"):
            orders_messages.append(msg.payload)
            await msg.ack()
            break

    async def consume_events() -> None:
        async for msg in subscriber.subscribe("events"):
            events_messages.append(msg.payload)
            await msg.ack()
            break

    orders_task = asyncio.create_task(consume_orders())
    events_task = asyncio.create_task(consume_events())
    await asyncio.sleep(0.1)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=subscriber.app),
        base_url="http://test",
    ) as client:
        await client.post("/orders", content=b"order data")
        await client.post("/events", content=b"event data")

    await orders_task
    await events_task
    await subscriber.close()

    assert orders_messages == [b"order data"]
    assert events_messages == [b"event data"]


@pytest.mark.anyio
async def test_subscriber_context_manager() -> None:
    """Subscriber works as async context manager."""
    async with HTTPSubscriber() as subscriber:
        assert not subscriber._closed

    assert subscriber._closed


@pytest.mark.anyio
async def test_nested_topic_path() -> None:
    """Subscriber handles nested topic paths."""
    subscriber = HTTPSubscriber()
    received_messages: list[bytes] = []

    async def consume() -> None:
        async for msg in subscriber.subscribe("orders/new"):
            received_messages.append(msg.payload)
            await msg.ack()
            break

    consumer_task = asyncio.create_task(consume())
    await asyncio.sleep(0.1)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=subscriber.app),
        base_url="http://test",
    ) as client:
        response = await client.post("/orders/new", content=b"nested")
        assert response.status_code == HTTPStatus.OK

    await consumer_task
    await subscriber.close()

    assert received_messages == [b"nested"]
