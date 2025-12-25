"""Tests for EventBus."""

from typing import Annotated

import anyio
import pytest
from pydantic import BaseModel

from natricine.cqrs import Depends, EventBus, PydanticMarshaler
from natricine.pubsub import InMemoryPubSub, Subscriber

pytestmark = pytest.mark.anyio

TIMEOUT_SECONDS = 2


class UserCreated(BaseModel):
    user_id: int
    name: str


class OrderPlaced(BaseModel):
    order_id: str


class TestEventBus:
    async def test_event_routed_to_handler(self) -> None:
        async with InMemoryPubSub() as pubsub:
            marshaler = PydanticMarshaler()
            bus = EventBus(pubsub, pubsub, marshaler)
            received: list[UserCreated] = []

            @bus.handler
            async def on_user_created(event: UserCreated) -> None:
                received.append(event)

            async def publish_event() -> None:
                await anyio.sleep(0.01)
                await bus.publish(UserCreated(user_id=1, name="Alice"))
                await anyio.sleep(0.02)
                await bus.close()

            with anyio.fail_after(TIMEOUT_SECONDS):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(bus.run)
                    tg.start_soon(publish_event)

            assert len(received) == 1
            assert received[0].user_id == 1

    async def test_multiple_handlers_same_event(self) -> None:
        async with InMemoryPubSub() as pubsub:
            marshaler = PydanticMarshaler()
            bus = EventBus(pubsub, pubsub, marshaler)
            handler1_received: list[UserCreated] = []
            handler2_received: list[UserCreated] = []

            @bus.handler
            async def handler1(event: UserCreated) -> None:
                handler1_received.append(event)

            @bus.handler
            async def handler2(event: UserCreated) -> None:
                handler2_received.append(event)

            async def publish_event() -> None:
                await anyio.sleep(0.01)
                await bus.publish(UserCreated(user_id=1, name="Alice"))
                await anyio.sleep(0.05)
                await bus.close()

            with anyio.fail_after(TIMEOUT_SECONDS):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(bus.run)
                    tg.start_soon(publish_event)

            assert len(handler1_received) == 1
            assert len(handler2_received) == 1

    async def test_handler_with_depends(self) -> None:
        async with InMemoryPubSub() as pubsub:
            marshaler = PydanticMarshaler()
            bus = EventBus(pubsub, pubsub, marshaler)
            results: list[tuple[UserCreated, str]] = []

            def get_notifier() -> str:
                return "email_notifier"

            @bus.handler
            async def on_user_created(
                event: UserCreated,
                notifier: Annotated[str, Depends(get_notifier)],
            ) -> None:
                results.append((event, notifier))

            async def publish_event() -> None:
                await anyio.sleep(0.01)
                await bus.publish(UserCreated(user_id=1, name="Test"))
                await anyio.sleep(0.02)
                await bus.close()

            with anyio.fail_after(TIMEOUT_SECONDS):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(bus.run)
                    tg.start_soon(publish_event)

            assert len(results) == 1
            assert results[0][0].name == "Test"
            assert results[0][1] == "email_notifier"

    async def test_sync_handler(self) -> None:
        async with InMemoryPubSub() as pubsub:
            marshaler = PydanticMarshaler()
            bus = EventBus(pubsub, pubsub, marshaler)
            received: list[UserCreated] = []

            @bus.handler
            def on_user_created_sync(event: UserCreated) -> None:
                received.append(event)

            async def publish_event() -> None:
                await anyio.sleep(0.01)
                await bus.publish(UserCreated(user_id=1, name="Sync"))
                await anyio.sleep(0.02)
                await bus.close()

            with anyio.fail_after(TIMEOUT_SECONDS):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(bus.run)
                    tg.start_soon(publish_event)

            assert len(received) == 1
            assert received[0].name == "Sync"

    async def test_mixed_sync_async_handlers(self) -> None:
        async with InMemoryPubSub() as pubsub:
            marshaler = PydanticMarshaler()
            bus = EventBus(pubsub, pubsub, marshaler)
            sync_received: list[UserCreated] = []
            async_received: list[UserCreated] = []

            @bus.handler
            def sync_handler(event: UserCreated) -> None:
                sync_received.append(event)

            @bus.handler
            async def async_handler(event: UserCreated) -> None:
                async_received.append(event)

            async def publish_event() -> None:
                await anyio.sleep(0.01)
                await bus.publish(UserCreated(user_id=1, name="Mixed"))
                await anyio.sleep(0.05)
                await bus.close()

            with anyio.fail_after(TIMEOUT_SECONDS):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(bus.run)
                    tg.start_soon(publish_event)

            assert len(sync_received) == 1
            assert len(async_received) == 1
            assert sync_received[0].name == "Mixed"
            assert async_received[0].name == "Mixed"


class TestEventBusSubscriberFactory:
    """Tests for subscriber_factory pattern."""

    async def test_factory_creates_subscriber_per_handler(self) -> None:
        """Test that subscriber_factory is called for each handler."""
        async with InMemoryPubSub() as pubsub:
            marshaler = PydanticMarshaler()
            created_subscribers: list[str] = []

            def subscriber_factory(handler_name: str) -> Subscriber:
                created_subscribers.append(handler_name)
                return pubsub

            bus = EventBus(
                pubsub,
                marshaler=marshaler,
                subscriber_factory=subscriber_factory,
            )
            received1: list[UserCreated] = []
            received2: list[UserCreated] = []

            @bus.handler
            async def on_user_created(event: UserCreated) -> None:
                received1.append(event)

            @bus.handler
            async def another_handler(event: UserCreated) -> None:
                received2.append(event)

            async def publish_and_close() -> None:
                await anyio.sleep(0.01)
                await bus.publish(UserCreated(user_id=1, name="Test"))
                await anyio.sleep(0.05)
                await bus.close()

            with anyio.fail_after(TIMEOUT_SECONDS):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(bus.run)
                    tg.start_soon(publish_and_close)

            # Factory should have been called for each handler
            expected_handlers = {"on_user_created", "another_handler"}
            assert set(created_subscribers) == expected_handlers

    async def test_validation_requires_subscriber_or_factory(self) -> None:
        """Test that either subscriber or subscriber_factory is required."""
        async with InMemoryPubSub() as pubsub:
            marshaler = PydanticMarshaler()

            with pytest.raises(ValueError, match="Must provide either"):
                EventBus(pubsub, marshaler=marshaler)


class TestEventBusGenerateTopic:
    """Tests for generate_topic custom topic generation."""

    async def test_generate_topic_overrides_default(self) -> None:
        """Test that generate_topic callback overrides default naming."""
        async with InMemoryPubSub() as pubsub:
            marshaler = PydanticMarshaler()
            generated_topics: list[str] = []

            def custom_topic_gen(event_name: str) -> str:
                topic = f"custom.{event_name.lower()}"
                generated_topics.append(topic)
                return topic

            bus = EventBus(
                pubsub,
                pubsub,
                marshaler=marshaler,
                generate_topic=custom_topic_gen,
            )
            received: list[UserCreated] = []

            @bus.handler
            async def on_user_created(event: UserCreated) -> None:
                received.append(event)

            async def publish_and_close() -> None:
                await anyio.sleep(0.01)
                await bus.publish(UserCreated(user_id=1, name="Test"))
                await anyio.sleep(0.02)
                await bus.close()

            with anyio.fail_after(TIMEOUT_SECONDS):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(bus.run)
                    tg.start_soon(publish_and_close)

            # Custom topic generator should have been used
            assert "custom.usercreated" in generated_topics
            assert len(received) == 1

    async def test_monotopic_pattern_single_type(self) -> None:
        """Test monotopic pattern - topic name customization works.

        Note: True monotopic fan-out with multiple event types requires
        infrastructure-level routing (e.g., SNS filter policies) or
        envelope patterns with type discriminators. This test verifies
        the generate_topic callback works for custom topic naming.
        """
        async with InMemoryPubSub() as pubsub:
            marshaler = PydanticMarshaler()

            # All events go to "events" topic instead of "event.{EventName}"
            bus = EventBus(
                pubsub,
                pubsub,
                marshaler=marshaler,
                generate_topic=lambda _: "events",
            )
            received: list[UserCreated] = []

            @bus.handler
            async def on_user_created(event: UserCreated) -> None:
                received.append(event)

            async def publish_and_close() -> None:
                await anyio.sleep(0.01)
                await bus.publish(UserCreated(user_id=1, name="Alice"))
                await bus.publish(UserCreated(user_id=2, name="Bob"))
                await anyio.sleep(0.05)
                await bus.close()

            with anyio.fail_after(TIMEOUT_SECONDS):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(bus.run)
                    tg.start_soon(publish_and_close)

            # Events published to "events" topic are received
            expected_names = ["Alice", "Bob"]
            assert [e.name for e in received] == expected_names
