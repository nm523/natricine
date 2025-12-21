import os

import pytest
from redis.asyncio import Redis


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def redis_available() -> bool:
    """Check if Redis is available for testing."""
    return os.environ.get("REDIS_URL") is not None


@pytest.fixture
async def redis_client():
    """Create a Redis client for testing."""
    url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    client = Redis.from_url(url, decode_responses=False)
    try:
        await client.ping()
        yield client
    except Exception:
        pytest.skip("Redis not available")
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
