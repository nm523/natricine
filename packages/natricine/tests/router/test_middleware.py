"""Tests for built-in middlewares."""

import anyio
import pytest

from natricine.pubsub import InMemoryPubSub, Message
from natricine.router import (
    POISON_HANDLER_KEY,
    POISON_REASON_KEY,
    POISON_SUBSCRIBER_KEY,
    PermanentError,
    dead_letter_queue,
    poison_queue,
    retry,
    timeout,
)

pytestmark = pytest.mark.anyio

RETRY_COUNT = 3
EXPECTED_ATTEMPTS_TWO = 2
EXPECTED_ATTEMPTS_THREE = 3


class TestRetryMiddleware:
    async def test_retry_on_failure(self) -> None:
        """Retry middleware should retry failed handlers."""
        attempts = 0

        async def failing_handler(msg: Message) -> None:
            nonlocal attempts
            attempts += 1
            if attempts < RETRY_COUNT:
                raise ValueError("Not yet")
            return None

        wrapped = retry(max_retries=RETRY_COUNT, delay=0.01, jitter=0)(failing_handler)
        await wrapped(Message(payload=b"test"))

        assert attempts == RETRY_COUNT

    async def test_retry_exhausted_raises(self) -> None:
        """Retry middleware should raise after max retries."""
        attempts = 0

        async def always_fails(msg: Message) -> None:
            nonlocal attempts
            attempts += 1
            raise ValueError("Always fails")

        wrapped = retry(max_retries=RETRY_COUNT, delay=0.01, jitter=0)(always_fails)

        with pytest.raises(ValueError, match="Always fails"):
            await wrapped(Message(payload=b"test"))

        expected_attempts = RETRY_COUNT + 1  # initial + retries
        assert attempts == expected_attempts

    async def test_retry_success_no_retry(self) -> None:
        """Retry middleware should not retry on success."""
        attempts = 0

        async def succeeds(msg: Message) -> None:
            nonlocal attempts
            attempts += 1
            return None

        wrapped = retry(max_retries=RETRY_COUNT, delay=0.01, jitter=0)(succeeds)
        await wrapped(Message(payload=b"test"))

        assert attempts == 1

    async def test_permanent_error_not_retried(self) -> None:
        """PermanentError should skip retries."""
        attempts = 0

        async def permanent_failure(msg: Message) -> None:
            nonlocal attempts
            attempts += 1
            raise PermanentError(ValueError("Don't retry this"))

        wrapped = retry(max_retries=RETRY_COUNT, delay=0.01, jitter=0)(
            permanent_failure
        )

        with pytest.raises(ValueError, match="Don't retry this"):
            await wrapped(Message(payload=b"test"))

        assert attempts == 1  # No retries

    async def test_retry_on_specific_exceptions(self) -> None:
        """retry_on should only retry specified exceptions."""
        attempts = 0

        async def type_error_handler(msg: Message) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise TypeError("Retry this")
            raise ValueError("Don't retry this")

        # Only retry TypeError, not ValueError
        wrapped = retry(
            max_retries=RETRY_COUNT, delay=0.01, jitter=0, retry_on=(TypeError,)
        )(type_error_handler)

        with pytest.raises(ValueError, match="Don't retry this"):
            await wrapped(Message(payload=b"test"))

        assert attempts == EXPECTED_ATTEMPTS_TWO  # Initial + 1 retry for TypeError

    async def test_on_retry_callback(self) -> None:
        """on_retry callback should be called before each retry."""
        attempts = 0
        retry_calls: list[tuple[int, Exception, Message]] = []

        async def failing_handler(msg: Message) -> None:
            nonlocal attempts
            attempts += 1
            if attempts < RETRY_COUNT:
                raise ValueError(f"Attempt {attempts}")
            return None

        def on_retry(attempt: int, exc: Exception, msg: Message) -> None:
            retry_calls.append((attempt, exc, msg))

        wrapped = retry(
            max_retries=RETRY_COUNT, delay=0.01, jitter=0, on_retry=on_retry
        )(failing_handler)
        await wrapped(Message(payload=b"test"))

        assert len(retry_calls) == RETRY_COUNT - 1
        assert retry_calls[0][0] == 1  # First retry
        assert "Attempt 1" in str(retry_calls[0][1])


class TestDeadLetterQueueMiddleware:
    async def test_dlq_catches_exception(self) -> None:
        """DLQ middleware should catch exceptions and publish to DLQ."""
        async with InMemoryPubSub() as pubsub:
            dlq_messages: list[Message] = []

            async def collect_dlq() -> None:
                async for msg in pubsub.subscribe("dlq.errors"):
                    dlq_messages.append(msg)
                    await msg.ack()
                    break

            async def failing_handler(msg: Message) -> None:
                raise ValueError("Handler failed")

            wrapped = dead_letter_queue(pubsub, "dlq.errors")(failing_handler)

            async with anyio.create_task_group() as tg:
                tg.start_soon(collect_dlq)
                await anyio.sleep(0.01)
                # Should not raise - DLQ catches it
                result = await wrapped(Message(payload=b"test"))
                await anyio.sleep(0.02)
                tg.cancel_scope.cancel()

            assert result is None
            assert len(dlq_messages) == 1
            assert dlq_messages[0].payload == b"test"
            assert dlq_messages[0].metadata["dlq.error"] == "Handler failed"
            assert dlq_messages[0].metadata["dlq.error_type"] == "ValueError"

    async def test_dlq_preserves_original_metadata(self) -> None:
        """DLQ should preserve original message metadata."""
        async with InMemoryPubSub() as pubsub:
            dlq_messages: list[Message] = []

            async def collect_dlq() -> None:
                async for msg in pubsub.subscribe("dlq.errors"):
                    dlq_messages.append(msg)
                    await msg.ack()
                    break

            async def failing_handler(msg: Message) -> None:
                raise ValueError("Failed")

            wrapped = dead_letter_queue(pubsub, "dlq.errors")(failing_handler)
            original = Message(payload=b"test", metadata={"custom": "value"})

            async with anyio.create_task_group() as tg:
                tg.start_soon(collect_dlq)
                await anyio.sleep(0.01)
                await wrapped(original)
                await anyio.sleep(0.02)
                tg.cancel_scope.cancel()

            assert dlq_messages[0].metadata["custom"] == "value"
            assert dlq_messages[0].metadata["dlq.original_uuid"] == str(original.uuid)

    async def test_dlq_catch_specific_exceptions(self) -> None:
        """DLQ should only catch specified exception types."""
        async with InMemoryPubSub() as pubsub:

            async def type_error_handler(msg: Message) -> None:
                raise TypeError("Not caught by DLQ")

            # Only catch ValueError, not TypeError
            wrapped = dead_letter_queue(pubsub, "dlq.errors", catch=(ValueError,))(
                type_error_handler
            )

            with pytest.raises(TypeError, match="Not caught by DLQ"):
                await wrapped(Message(payload=b"test"))

    async def test_dlq_on_dlq_callback(self) -> None:
        """on_dlq callback should be called when message sent to DLQ."""
        async with InMemoryPubSub() as pubsub:
            callback_calls: list[tuple[Message, Exception]] = []

            def on_dlq(msg: Message, exc: Exception) -> None:
                callback_calls.append((msg, exc))

            async def failing_handler(msg: Message) -> None:
                raise ValueError("Failed")

            wrapped = dead_letter_queue(pubsub, "dlq.errors", on_dlq=on_dlq)(
                failing_handler
            )
            original = Message(payload=b"test")
            await wrapped(original)

            assert len(callback_calls) == 1
            assert callback_calls[0][0].uuid == original.uuid
            assert isinstance(callback_calls[0][1], ValueError)

    async def test_dlq_with_retry_integration(self) -> None:
        """DLQ should work with retry middleware."""
        async with InMemoryPubSub() as pubsub:
            dlq_messages: list[Message] = []
            attempts = 0

            async def collect_dlq() -> None:
                async for msg in pubsub.subscribe("dlq.errors"):
                    dlq_messages.append(msg)
                    await msg.ack()
                    break

            async def always_fails(msg: Message) -> None:
                nonlocal attempts
                attempts += 1
                raise ValueError("Always fails")

            # DLQ wraps retry - catches exception after retries exhausted
            retry_mw = retry(max_retries=2, delay=0.01, jitter=0)
            dlq_mw = dead_letter_queue(pubsub, "dlq.errors")
            wrapped = dlq_mw(retry_mw(always_fails))

            async with anyio.create_task_group() as tg:
                tg.start_soon(collect_dlq)
                await anyio.sleep(0.01)
                result = await wrapped(Message(payload=b"test"))
                await anyio.sleep(0.02)
                tg.cancel_scope.cancel()

            assert result is None  # DLQ swallowed the exception
            assert attempts == EXPECTED_ATTEMPTS_THREE  # Initial + 2 retries
            assert len(dlq_messages) == 1
            assert dlq_messages[0].metadata["dlq.error"] == "Always fails"


class TestPoisonQueueMiddleware:
    """Tests for watermill-compatible poison queue middleware."""

    async def test_poison_catches_exception(self) -> None:
        """Poison queue should catch exceptions and publish with watermill keys."""
        async with InMemoryPubSub() as pubsub:
            poison_messages: list[Message] = []

            async def collect_poison() -> None:
                async for msg in pubsub.subscribe("poison.errors"):
                    poison_messages.append(msg)
                    await msg.ack()
                    break

            async def failing_handler(msg: Message) -> None:
                raise ValueError("Handler failed")

            wrapped = poison_queue(pubsub, "poison.errors")(failing_handler)

            async with anyio.create_task_group() as tg:
                tg.start_soon(collect_poison)
                await anyio.sleep(0.01)
                result = await wrapped(Message(payload=b"test"))
                await anyio.sleep(0.02)
                tg.cancel_scope.cancel()

            assert result is None
            assert len(poison_messages) == 1
            assert poison_messages[0].payload == b"test"
            # Watermill-compatible key
            assert poison_messages[0].metadata[POISON_REASON_KEY] == "Handler failed"

    async def test_poison_includes_handler_and_subscriber(self) -> None:
        """Poison queue should include handler and subscriber names."""
        async with InMemoryPubSub() as pubsub:
            poison_messages: list[Message] = []

            async def collect_poison() -> None:
                async for msg in pubsub.subscribe("poison.errors"):
                    poison_messages.append(msg)
                    await msg.ack()
                    break

            async def failing_handler(msg: Message) -> None:
                raise ValueError("Failed")

            wrapped = poison_queue(
                pubsub,
                "poison.errors",
                handler_name="my_handler",
                subscriber_name="my_subscriber",
            )(failing_handler)

            async with anyio.create_task_group() as tg:
                tg.start_soon(collect_poison)
                await anyio.sleep(0.01)
                await wrapped(Message(payload=b"test"))
                await anyio.sleep(0.02)
                tg.cancel_scope.cancel()

            assert poison_messages[0].metadata[POISON_HANDLER_KEY] == "my_handler"
            assert poison_messages[0].metadata[POISON_SUBSCRIBER_KEY] == "my_subscriber"

    async def test_poison_preserves_original_metadata(self) -> None:
        """Poison queue should preserve original message metadata."""
        async with InMemoryPubSub() as pubsub:
            poison_messages: list[Message] = []

            async def collect_poison() -> None:
                async for msg in pubsub.subscribe("poison.errors"):
                    poison_messages.append(msg)
                    await msg.ack()
                    break

            async def failing_handler(msg: Message) -> None:
                raise ValueError("Failed")

            wrapped = poison_queue(pubsub, "poison.errors")(failing_handler)
            original = Message(payload=b"test", metadata={"correlation_id": "abc123"})

            async with anyio.create_task_group() as tg:
                tg.start_soon(collect_poison)
                await anyio.sleep(0.01)
                await wrapped(original)
                await anyio.sleep(0.02)
                tg.cancel_scope.cancel()

            assert poison_messages[0].metadata["correlation_id"] == "abc123"

    async def test_poison_with_retry_integration(self) -> None:
        """Poison queue should work with retry middleware."""
        async with InMemoryPubSub() as pubsub:
            poison_messages: list[Message] = []
            attempts = 0

            async def collect_poison() -> None:
                async for msg in pubsub.subscribe("poison.errors"):
                    poison_messages.append(msg)
                    await msg.ack()
                    break

            async def always_fails(msg: Message) -> None:
                nonlocal attempts
                attempts += 1
                raise ValueError("Always fails")

            # Poison queue wraps retry
            retry_mw = retry(max_retries=2, delay=0.01, jitter=0)
            poison_mw = poison_queue(
                pubsub, "poison.errors", handler_name="always_fails"
            )
            wrapped = poison_mw(retry_mw(always_fails))

            async with anyio.create_task_group() as tg:
                tg.start_soon(collect_poison)
                await anyio.sleep(0.01)
                result = await wrapped(Message(payload=b"test"))
                await anyio.sleep(0.02)
                tg.cancel_scope.cancel()

            assert result is None
            assert attempts == EXPECTED_ATTEMPTS_THREE  # Initial + 2 retries
            assert len(poison_messages) == 1
            assert poison_messages[0].metadata[POISON_REASON_KEY] == "Always fails"
            assert poison_messages[0].metadata[POISON_HANDLER_KEY] == "always_fails"


class TestTimeoutMiddleware:
    async def test_timeout_cancels_slow_handler(self) -> None:
        """Timeout middleware should cancel slow handlers."""

        async def slow_handler(msg: Message) -> None:
            await anyio.sleep(10)
            return None

        wrapped = timeout(0.05)(slow_handler)

        with pytest.raises(TimeoutError):
            await wrapped(Message(payload=b"test"))

    async def test_timeout_allows_fast_handler(self) -> None:
        """Timeout middleware should allow fast handlers."""
        called = False

        async def fast_handler(msg: Message) -> None:
            nonlocal called
            called = True
            return None

        wrapped = timeout(1.0)(fast_handler)
        await wrapped(Message(payload=b"test"))

        assert called
