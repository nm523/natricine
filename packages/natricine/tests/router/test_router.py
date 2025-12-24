"""Tests for Router."""

import anyio
import pytest

from natricine.pubsub import InMemoryPubSub, Message
from natricine.router import Router, RouterConfig

pytestmark = pytest.mark.anyio

TIMEOUT_SECONDS = 2
EXPECTED_MIDDLEWARE_CALLS = 2


class TestRouterBasic:
    async def test_handler_receives_messages(self) -> None:
        """Handler should receive messages from subscriber."""
        async with InMemoryPubSub() as pubsub:
            received: list[Message] = []

            async def handler(msg: Message) -> None:
                received.append(msg)

            router = Router()
            router.add_no_publisher_handler(
                name="test-handler",
                subscribe_topic="input",
                subscriber=pubsub,
                handler_func=handler,
            )

            async def publish() -> None:
                await anyio.sleep(0.01)
                await pubsub.publish("input", Message(payload=b"hello"))
                await anyio.sleep(0.01)
                await router.close()

            with anyio.fail_after(TIMEOUT_SECONDS):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(router.run)
                    tg.start_soon(publish)

            assert len(received) == 1
            assert received[0].payload == b"hello"

    async def test_handler_publishes_output(self) -> None:
        """Handler can publish output messages."""
        async with InMemoryPubSub() as pubsub:
            output_received: list[Message] = []

            async def transform(msg: Message) -> list[Message] | None:
                return [Message(payload=msg.payload.upper())]

            async def collector(msg: Message) -> None:
                output_received.append(msg)

            router = Router()
            router.add_handler(
                name="transform",
                subscribe_topic="input",
                subscriber=pubsub,
                publish_topic="output",
                publisher=pubsub,
                handler_func=transform,
            )
            router.add_no_publisher_handler(
                name="collector",
                subscribe_topic="output",
                subscriber=pubsub,
                handler_func=collector,
            )

            async def publish() -> None:
                await anyio.sleep(0.01)
                await pubsub.publish("input", Message(payload=b"hello"))
                await anyio.sleep(0.05)
                await router.close()

            with anyio.fail_after(TIMEOUT_SECONDS):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(router.run)
                    tg.start_soon(publish)

            assert len(output_received) == 1
            assert output_received[0].payload == b"HELLO"

    async def test_message_acked_on_success(self) -> None:
        """Message should be acked when handler succeeds."""
        async with InMemoryPubSub() as pubsub:
            processed_msg: Message | None = None

            async def handler(msg: Message) -> None:
                nonlocal processed_msg
                processed_msg = msg

            router = Router()
            router.add_no_publisher_handler(
                name="test",
                subscribe_topic="input",
                subscriber=pubsub,
                handler_func=handler,
            )

            async def publish() -> None:
                await anyio.sleep(0.01)
                await pubsub.publish("input", Message(payload=b"test"))
                await anyio.sleep(0.01)
                await router.close()

            with anyio.fail_after(TIMEOUT_SECONDS):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(router.run)
                    tg.start_soon(publish)

            assert processed_msg is not None
            assert processed_msg.acked

    async def test_message_nacked_on_failure(self) -> None:
        """Message should be nacked when handler fails."""
        async with InMemoryPubSub() as pubsub:
            processed_msg: Message | None = None

            async def failing_handler(msg: Message) -> None:
                nonlocal processed_msg
                processed_msg = msg
                raise ValueError("Handler failed")

            router = Router()
            router.add_no_publisher_handler(
                name="test",
                subscribe_topic="input",
                subscriber=pubsub,
                handler_func=failing_handler,
            )

            async def publish() -> None:
                await anyio.sleep(0.01)
                await pubsub.publish("input", Message(payload=b"test"))

            # Handler failure crashes the router (use recoverer middleware to prevent)
            with anyio.fail_after(TIMEOUT_SECONDS):
                with pytest.raises(ExceptionGroup):
                    async with anyio.create_task_group() as tg:
                        tg.start_soon(router.run)
                        tg.start_soon(publish)

            assert processed_msg is not None
            assert processed_msg.nacked


class TestRouterMiddleware:
    async def test_router_middleware_applied_to_all_handlers(self) -> None:
        """Router-level middleware applies to all handlers."""
        async with InMemoryPubSub() as pubsub:
            middleware_calls: list[str] = []

            def tracking_middleware(name: str):
                def middleware(next_handler):
                    async def handler(msg: Message) -> None:
                        middleware_calls.append(name)
                        return await next_handler(msg)

                    return handler

                return middleware

            async def handler1(msg: Message) -> None:
                pass

            async def handler2(msg: Message) -> None:
                pass

            router = Router()
            router.add_middleware(tracking_middleware("global"))
            router.add_no_publisher_handler("h1", "topic1", pubsub, handler1)
            router.add_no_publisher_handler("h2", "topic2", pubsub, handler2)

            async def publish() -> None:
                await anyio.sleep(0.01)
                await pubsub.publish("topic1", Message(payload=b"1"))
                await pubsub.publish("topic2", Message(payload=b"2"))
                await anyio.sleep(0.02)
                await router.close()

            with anyio.fail_after(TIMEOUT_SECONDS):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(router.run)
                    tg.start_soon(publish)

            assert middleware_calls.count("global") == EXPECTED_MIDDLEWARE_CALLS

    async def test_handler_specific_middleware(self) -> None:
        """Handler-specific middleware only applies to that handler."""
        async with InMemoryPubSub() as pubsub:
            middleware_calls: list[str] = []

            def tracking_middleware(name: str):
                def middleware(next_handler):
                    async def handler(msg: Message) -> None:
                        middleware_calls.append(name)
                        return await next_handler(msg)

                    return handler

                return middleware

            async def handler1(msg: Message) -> None:
                pass

            async def handler2(msg: Message) -> None:
                pass

            router = Router()
            h1_middlewares = [tracking_middleware("h1")]
            router.add_no_publisher_handler(
                "h1", "topic1", pubsub, handler1, middlewares=h1_middlewares
            )
            router.add_no_publisher_handler("h2", "topic2", pubsub, handler2)

            async def publish() -> None:
                await anyio.sleep(0.01)
                await pubsub.publish("topic1", Message(payload=b"1"))
                await pubsub.publish("topic2", Message(payload=b"2"))
                await anyio.sleep(0.02)
                await router.close()

            with anyio.fail_after(TIMEOUT_SECONDS):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(router.run)
                    tg.start_soon(publish)

            assert middleware_calls == ["h1"]


class TestRouterGracefulShutdown:
    async def test_in_flight_property(self) -> None:
        """Router should track in-flight messages."""
        async with InMemoryPubSub() as pubsub:
            in_flight_during_handler = 0

            async def handler(msg: Message) -> None:
                nonlocal in_flight_during_handler
                in_flight_during_handler = router.in_flight
                await anyio.sleep(0.01)

            router = Router()
            router.add_no_publisher_handler(
                name="test",
                subscribe_topic="input",
                subscriber=pubsub,
                handler_func=handler,
            )

            async def publish() -> None:
                await anyio.sleep(0.01)
                await pubsub.publish("input", Message(payload=b"test"))
                await anyio.sleep(0.05)
                await router.close()

            with anyio.fail_after(TIMEOUT_SECONDS):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(router.run)
                    tg.start_soon(publish)

            assert in_flight_during_handler == 1
            assert router.in_flight == 0

    async def test_graceful_close_waits_for_in_flight(self) -> None:
        """Router.close() should wait for in-flight messages to complete."""
        async with InMemoryPubSub() as pubsub:
            handler_started = anyio.Event()
            handler_completed = False

            async def slow_handler(msg: Message) -> None:
                nonlocal handler_completed
                handler_started.set()
                await anyio.sleep(0.1)  # Simulate slow processing
                handler_completed = True

            router = Router(config=RouterConfig(close_timeout_s=5.0))
            router.add_no_publisher_handler(
                name="test",
                subscribe_topic="input",
                subscriber=pubsub,
                handler_func=slow_handler,
            )

            async def publish_and_close() -> None:
                await anyio.sleep(0.01)
                await pubsub.publish("input", Message(payload=b"test"))
                await handler_started.wait()
                # Close while handler is still processing
                await router.close()

            with anyio.fail_after(TIMEOUT_SECONDS):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(router.run)
                    tg.start_soon(publish_and_close)

            # Handler should have completed before close() returned
            assert handler_completed

    async def test_graceful_close_times_out(self) -> None:
        """Router.close() should force cancel after timeout."""
        async with InMemoryPubSub() as pubsub:
            handler_started = anyio.Event()
            handler_cancelled = False

            async def very_slow_handler(msg: Message) -> None:
                nonlocal handler_cancelled
                handler_started.set()
                try:
                    await anyio.sleep(10)  # Very slow - should be cancelled
                except anyio.get_cancelled_exc_class():
                    handler_cancelled = True
                    raise

            router = Router(config=RouterConfig(close_timeout_s=0.1))
            router.add_no_publisher_handler(
                name="test",
                subscribe_topic="input",
                subscriber=pubsub,
                handler_func=very_slow_handler,
            )

            async def publish_and_close() -> None:
                await anyio.sleep(0.01)
                await pubsub.publish("input", Message(payload=b"test"))
                await handler_started.wait()
                await router.close()

            with anyio.fail_after(TIMEOUT_SECONDS):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(router.run)
                    tg.start_soon(publish_and_close)

            assert handler_cancelled

    async def test_is_closing_property(self) -> None:
        """Router.is_closing should be True during shutdown."""
        async with InMemoryPubSub() as pubsub:
            handler_started = anyio.Event()
            is_closing_during_handler = False

            async def slow_handler(msg: Message) -> None:
                nonlocal is_closing_during_handler
                handler_started.set()
                # Sleep a bit to let close() be called
                await anyio.sleep(0.05)
                is_closing_during_handler = router.is_closing

            router = Router(config=RouterConfig(close_timeout_s=1.0))
            router.add_no_publisher_handler(
                name="test",
                subscribe_topic="input",
                subscriber=pubsub,
                handler_func=slow_handler,
            )

            async def publish_and_close() -> None:
                await anyio.sleep(0.01)
                await pubsub.publish("input", Message(payload=b"test"))
                await handler_started.wait()
                # Close while handler is processing
                await router.close()

            with anyio.fail_after(TIMEOUT_SECONDS):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(router.run)
                    tg.start_soon(publish_and_close)

            assert is_closing_during_handler

    async def test_close_without_running_is_noop(self) -> None:
        """Calling close() when not running should do nothing."""
        router = Router()
        await router.close()  # Should not raise
