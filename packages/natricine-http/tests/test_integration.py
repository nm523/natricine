"""Integration tests for HTTPSubscriber with Starlette and FastAPI."""

import asyncio
from http import HTTPStatus

import httpx
import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from natricine.backends.http import HTTPPublisher, HTTPPublisherConfig, HTTPSubscriber
from natricine.pubsub import Message


class TestStarletteIntegration:
    """Tests for pure Starlette deployment."""

    @pytest.mark.anyio
    async def test_mount_in_starlette_app(self) -> None:
        """HTTPSubscriber mounts in a Starlette app."""
        subscriber = HTTPSubscriber()

        app = Starlette(
            routes=[
                Mount("/webhooks", app=subscriber.app),
            ],
        )

        received: list[bytes] = []

        async def consume() -> None:
            async for msg in subscriber.subscribe("orders"):
                received.append(msg.payload)
                await msg.ack()
                break

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.1)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/webhooks/orders",
                content=b'{"order_id": 123}',
            )
            assert response.status_code == HTTPStatus.OK

        await task
        await subscriber.close()

        assert received == [b'{"order_id": 123}']

    @pytest.mark.anyio
    async def test_starlette_with_other_routes(self) -> None:
        """HTTPSubscriber coexists with other Starlette routes."""
        subscriber = HTTPSubscriber()

        async def health(request: httpx.Request) -> JSONResponse:
            return JSONResponse({"status": "ok"})

        app = Starlette(
            routes=[
                Route("/health", health),
                Mount("/webhooks", app=subscriber.app),
            ],
        )

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # Health endpoint works
            response = await client.get("/health")
            assert response.status_code == HTTPStatus.OK
            assert response.json() == {"status": "ok"}

        await subscriber.close()


class TestFastAPIIntegration:
    """Tests for FastAPI deployment."""

    @pytest.mark.anyio
    async def test_mount_in_fastapi_app(self) -> None:
        """HTTPSubscriber mounts in a FastAPI app."""
        FastAPI = pytest.importorskip("fastapi").FastAPI

        subscriber = HTTPSubscriber()
        app = FastAPI()
        app.mount("/webhooks", subscriber.app)

        received: list[bytes] = []

        async def consume() -> None:
            async for msg in subscriber.subscribe("events"):
                received.append(msg.payload)
                await msg.ack()
                break

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.1)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/webhooks/events",
                content=b"event data",
                headers={"X-Natricine-Meta-source": "test"},
            )
            assert response.status_code == HTTPStatus.OK

        await task
        await subscriber.close()

        assert received == [b"event data"]

    @pytest.mark.anyio
    async def test_fastapi_with_other_endpoints(self) -> None:
        """HTTPSubscriber coexists with FastAPI endpoints."""
        FastAPI = pytest.importorskip("fastapi").FastAPI

        subscriber = HTTPSubscriber()
        app = FastAPI()
        app.mount("/webhooks", subscriber.app)

        @app.get("/api/status")
        async def status() -> dict[str, str]:
            return {"status": "running"}

        @app.post("/api/orders")
        async def create_order() -> dict[str, int]:
            return {"id": 1}

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # FastAPI endpoints work
            response = await client.get("/api/status")
            assert response.status_code == HTTPStatus.OK
            assert response.json() == {"status": "running"}

            response = await client.post("/api/orders")
            assert response.status_code == HTTPStatus.OK
            assert response.json() == {"id": 1}

        await subscriber.close()

    @pytest.mark.anyio
    async def test_fastapi_background_consumer(self) -> None:
        """HTTPSubscriber works with background consumer pattern."""
        FastAPI = pytest.importorskip("fastapi").FastAPI

        subscriber = HTTPSubscriber()
        app = FastAPI()
        app.mount("/webhooks", subscriber.app)

        received: list[bytes] = []

        async def consume() -> None:
            async for msg in subscriber.subscribe("orders"):
                received.append(msg.payload)
                await msg.ack()
                break

        # Start consumer before making request
        task = asyncio.create_task(consume())
        await asyncio.sleep(0.1)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post("/webhooks/orders", content=b"order")
            assert response.status_code == HTTPStatus.OK

        await task
        await subscriber.close()

        assert received == [b"order"]


class TestEndToEnd:
    """End-to-end tests with publisher and subscriber."""

    @pytest.mark.anyio
    async def test_publisher_to_subscriber(self) -> None:
        """Publisher can send to subscriber via HTTP."""
        subscriber = HTTPSubscriber()
        app = Starlette(routes=[Mount("/", app=subscriber.app)])

        received: list[Message] = []

        async def consume() -> None:
            async for msg in subscriber.subscribe("orders"):
                received.append(msg)
                await msg.ack()
                break

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.1)

        # Use ASGI transport to connect publisher to subscriber
        transport = httpx.ASGITransport(app=app)
        config = HTTPPublisherConfig(base_url="http://test")

        async with HTTPPublisher(config) as publisher:
            publisher._client = httpx.AsyncClient(
                transport=transport,
                base_url=config.base_url,
            )
            await publisher.publish(
                "orders",
                Message(
                    payload=b'{"id": 1}',
                    metadata={"trace_id": "abc123"},
                ),
            )

        await task
        await subscriber.close()

        assert len(received) == 1
        assert received[0].payload == b'{"id": 1}'
        assert received[0].metadata["trace_id"] == "abc123"
