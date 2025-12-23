"""Test fixtures for natricine-redisstream."""

import os

import pytest
from redis.asyncio import Redis
from testcontainers.redis import RedisContainer


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def redis_container():
    """Start a Redis container for the test session."""
    # Skip container if REDIS_URL is set (allows using external Redis)
    if os.environ.get("REDIS_URL"):
        yield None
        return

    # Disable Ryuk for podman compatibility
    os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

    with RedisContainer() as container:
        yield container


@pytest.fixture
async def redis_client(redis_container):
    """Create a Redis client for testing."""
    if redis_container is None:
        # Use external Redis from REDIS_URL
        url = os.environ["REDIS_URL"]
    else:
        # Use testcontainers Redis
        host = redis_container.get_container_host_ip()
        port = redis_container.get_exposed_port(6379)
        url = f"redis://{host}:{port}"

    client = Redis.from_url(url, decode_responses=False)
    try:
        await client.ping()
        yield client
    finally:
        await client.aclose()


@pytest.fixture
async def clean_stream(redis_client):
    """Fixture to clean up test streams."""
    streams_to_clean: list[str] = []

    def register(stream_name: str) -> str:
        streams_to_clean.append(stream_name)
        return stream_name

    yield register

    # Cleanup
    for stream in streams_to_clean:
        await redis_client.delete(stream)
