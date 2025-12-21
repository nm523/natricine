"""Tests for EventBus."""

from typing import Annotated

import anyio
import pytest
from pydantic import BaseModel

from natricine_cqrs import Depends, EventBus, PydanticMarshaler
from natricine_pubsub import InMemoryPubSub

pytestmark = pytest.mark.anyio

TIMEOUT_SECONDS = 2


class UserCreated(BaseModel):
    user_id: int
    name: str


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
