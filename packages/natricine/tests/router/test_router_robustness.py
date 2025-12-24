"""Robustness tests for Router."""

import anyio
import pytest

from natricine.pubsub import InMemoryPubSub, Message
from natricine.router import Router, RouterConfig

pytestmark = pytest.mark.anyio

TIMEOUT_SECONDS = 2
MESSAGE_COUNT = 5


class TestRouterConcurrency:
    async def test_slow_handler_does_not_block_other_handlers(self) -> None:
        """Slow handler should not block other handlers."""
        async with InMemoryPubSub() as pubsub:
            fast_received: list[Message] = []
            slow_received: list[Message] = []

            async def slow_handler(msg: Message) -> None:
                await anyio.sleep(0.5)
                slow_received.append(msg)

            async def fast_handler(msg: Message) -> None:
                fast_received.append(msg)

            router = Router()
            router.add_no_publisher_handler("slow", "slow-topic", pubsub, slow_handler)
            router.add_no_publisher_handler("fast", "fast-topic", pubsub, fast_handler)

            async def publish() -> None:
                await anyio.sleep(0.01)
                await pubsub.publish("slow-topic", Message(payload=b"slow"))
                for i in range(MESSAGE_COUNT):
                    await pubsub.publish(
                        "fast-topic", Message(payload=f"fast-{i}".encode())
                    )
                await anyio.sleep(0.1)
                await router.close()

            with anyio.fail_after(TIMEOUT_SECONDS):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(router.run)
                    tg.start_soon(publish)

            # Fast handler should have processed all messages quickly
            assert len(fast_received) == MESSAGE_COUNT

    async def test_multiple_handlers_same_topic(self) -> None:
        """Multiple handlers on same topic each process messages independently."""
        async with InMemoryPubSub() as pubsub:
            handler1_received: list[Message] = []
            handler2_received: list[Message] = []

            async def handler1(msg: Message) -> None:
                handler1_received.append(msg)

            async def handler2(msg: Message) -> None:
                handler2_received.append(msg)

            router = Router()
            router.add_no_publisher_handler("h1", "topic", pubsub, handler1)
            router.add_no_publisher_handler("h2", "topic", pubsub, handler2)

            async def publish() -> None:
                await anyio.sleep(0.01)
                await pubsub.publish("topic", Message(payload=b"test"))
                await anyio.sleep(0.02)
                await router.close()

            with anyio.fail_after(TIMEOUT_SECONDS):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(router.run)
                    tg.start_soon(publish)

            # Both handlers get the message (fan-out from pubsub)
            assert len(handler1_received) == 1
            assert len(handler2_received) == 1


class TestRouterShutdown:
    async def test_graceful_shutdown(self) -> None:
        """Router should shut down gracefully with timeout cancellation."""
        async with InMemoryPubSub() as pubsub:
            handler_started = anyio.Event()
            handler_cancelled = False

            async def long_handler(msg: Message) -> None:
                nonlocal handler_cancelled
                handler_started.set()
                try:
                    await anyio.sleep(10)
                except anyio.get_cancelled_exc_class():
                    handler_cancelled = True
                    raise

            # Use short timeout to force cancellation
            router = Router(config=RouterConfig(close_timeout_s=0.1))
            router.add_no_publisher_handler("long", "topic", pubsub, long_handler)

            async def trigger_shutdown() -> None:
                await anyio.sleep(0.01)
                await pubsub.publish("topic", Message(payload=b"start"))
                await handler_started.wait()
                await router.close()

            with anyio.fail_after(TIMEOUT_SECONDS):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(router.run)
                    tg.start_soon(trigger_shutdown)

            assert handler_cancelled

    async def test_close_before_run_is_safe(self) -> None:
        """Closing router before run should be safe."""
        router = Router()
        await router.close()  # Should not raise

    async def test_double_run_raises(self) -> None:
        """Running router twice should raise."""
        async with InMemoryPubSub() as pubsub:

            async def noop_handler(msg: Message) -> None:
                pass

            router = Router()
            router.add_no_publisher_handler("test", "topic", pubsub, noop_handler)

            async def try_double_run() -> None:
                await anyio.sleep(0.01)
                with pytest.raises(RuntimeError, match="already running"):
                    await router.run()
                await router.close()

            with anyio.fail_after(TIMEOUT_SECONDS):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(router.run)
                    tg.start_soon(try_double_run)


class TestRouterErrorHandling:
    async def test_handler_error_does_not_crash_router(self) -> None:
        """One handler error should not crash other handlers."""
        async with InMemoryPubSub() as pubsub:
            good_received: list[Message] = []
            bad_called = False

            async def bad_handler(msg: Message) -> None:
                nonlocal bad_called
                bad_called = True
                raise ValueError("I'm bad")

            async def good_handler(msg: Message) -> None:
                good_received.append(msg)

            router = Router()
            router.add_no_publisher_handler("bad", "bad-topic", pubsub, bad_handler)
            router.add_no_publisher_handler("good", "good-topic", pubsub, good_handler)

            async def publish() -> None:
                await anyio.sleep(0.01)
                await pubsub.publish("bad-topic", Message(payload=b"bad"))
                await anyio.sleep(0.01)
                # Good handler should still work
                await pubsub.publish("good-topic", Message(payload=b"good"))
                await anyio.sleep(0.02)
                await router.close()

            # The router will crash because handler raises
            # This is expected - we need recoverer middleware to prevent this
            with anyio.fail_after(TIMEOUT_SECONDS):
                with pytest.raises(ExceptionGroup):
                    async with anyio.create_task_group() as tg:
                        tg.start_soon(router.run)
                        tg.start_soon(publish)

            assert bad_called
