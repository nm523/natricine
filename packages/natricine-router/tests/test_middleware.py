"""Tests for built-in middlewares."""

import anyio
import pytest

from natricine_pubsub import Message
from natricine_router import retry, timeout

pytestmark = pytest.mark.anyio

RETRY_COUNT = 3


class TestRetryMiddleware:
    async def test_retry_on_failure(self) -> None:
        """Retry middleware should retry failed handlers."""
        attempts = 0

        async def failing_handler(msg: Message) -> list[Message] | None:
            nonlocal attempts
            attempts += 1
            if attempts < RETRY_COUNT:
                raise ValueError("Not yet")
            return None

        wrapped = retry(max_retries=RETRY_COUNT, delay=0.01)(failing_handler)
        await wrapped(Message(payload=b"test"))

        assert attempts == RETRY_COUNT

    async def test_retry_exhausted_raises(self) -> None:
        """Retry middleware should raise after max retries."""
        attempts = 0

        async def always_fails(msg: Message) -> list[Message] | None:
            nonlocal attempts
            attempts += 1
            raise ValueError("Always fails")

        wrapped = retry(max_retries=RETRY_COUNT, delay=0.01)(always_fails)

        with pytest.raises(ValueError, match="Always fails"):
            await wrapped(Message(payload=b"test"))

        expected_attempts = RETRY_COUNT + 1  # initial + retries
        assert attempts == expected_attempts

    async def test_retry_success_no_retry(self) -> None:
        """Retry middleware should not retry on success."""
        attempts = 0

        async def succeeds(msg: Message) -> list[Message] | None:
            nonlocal attempts
            attempts += 1
            return None

        wrapped = retry(max_retries=RETRY_COUNT, delay=0.01)(succeeds)
        await wrapped(Message(payload=b"test"))

        assert attempts == 1


class TestTimeoutMiddleware:
    async def test_timeout_cancels_slow_handler(self) -> None:
        """Timeout middleware should cancel slow handlers."""

        async def slow_handler(msg: Message) -> list[Message] | None:
            await anyio.sleep(10)
            return None

        wrapped = timeout(0.05)(slow_handler)

        with pytest.raises(TimeoutError):
            await wrapped(Message(payload=b"test"))

    async def test_timeout_allows_fast_handler(self) -> None:
        """Timeout middleware should allow fast handlers."""
        called = False

        async def fast_handler(msg: Message) -> list[Message] | None:
            nonlocal called
            called = True
            return None

        wrapped = timeout(1.0)(fast_handler)
        await wrapped(Message(payload=b"test"))

        assert called
