"""Tests for CommandRouter and EventRouter."""

import anyio
import pytest
from pydantic import BaseModel

from natricine.cqrs import (
    CommandBus,
    CommandRouter,
    EventBus,
    EventRouter,
    PydanticMarshaler,
)
from natricine.pubsub import InMemoryPubSub

pytestmark = pytest.mark.anyio

TIMEOUT_SECONDS = 2
EXPECTED_HANDLER_COUNT = 2


class CreateUser(BaseModel):
    user_id: int
    name: str


class DeleteUser(BaseModel):
    user_id: int


class UserCreated(BaseModel):
    user_id: int
    name: str


class TestCommandRouter:
    async def test_register_handler(self) -> None:
        """Handler can be registered on a router."""
        router = CommandRouter()

        @router.handler
        async def handle_create(cmd: CreateUser) -> None:
            pass

        assert CreateUser in router._handlers
        assert router._handlers[CreateUser] is handle_create

    async def test_include_router_in_bus(self) -> None:
        """Handlers from router are included in bus and receive commands."""
        async with InMemoryPubSub() as pubsub:
            marshaler = PydanticMarshaler()
            router = CommandRouter()
            received: list[CreateUser] = []

            @router.handler
            async def handle_create(cmd: CreateUser) -> None:
                received.append(cmd)

            bus = CommandBus(pubsub, pubsub, marshaler)
            bus.include_router(router)

            async def send_command() -> None:
                await anyio.sleep(0.01)
                await bus.send(CreateUser(user_id=1, name="Alice"))
                await anyio.sleep(0.02)
                await bus.close()

            with anyio.fail_after(TIMEOUT_SECONDS):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(bus.run)
                    tg.start_soon(send_command)

            assert len(received) == 1
            assert received[0].name == "Alice"

    async def test_include_router_with_prefix(self) -> None:
        """Router prefix is prepended to topic names."""
        async with InMemoryPubSub() as pubsub:
            marshaler = PydanticMarshaler()
            router = CommandRouter()
            received: list[CreateUser] = []

            @router.handler
            async def handle_create(cmd: CreateUser) -> None:
                received.append(cmd)

            bus = CommandBus(pubsub, pubsub, marshaler)
            bus.include_router(router, prefix="users.")

            async def send_command() -> None:
                await anyio.sleep(0.01)
                await bus.send(CreateUser(user_id=1, name="Bob"))
                await anyio.sleep(0.02)
                await bus.close()

            with anyio.fail_after(TIMEOUT_SECONDS):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(bus.run)
                    tg.start_soon(send_command)

            assert len(received) == 1
            assert received[0].name == "Bob"

    async def test_duplicate_handler_raises(self) -> None:
        """Including router with duplicate command type raises ValueError."""
        async with InMemoryPubSub() as pubsub:
            marshaler = PydanticMarshaler()
            bus = CommandBus(pubsub, pubsub, marshaler)

            @bus.handler
            async def handle_create_on_bus(cmd: CreateUser) -> None:
                pass

            router = CommandRouter()

            @router.handler
            async def handle_create_on_router(cmd: CreateUser) -> None:
                pass

            with pytest.raises(ValueError, match="Handler already registered"):
                bus.include_router(router)

    async def test_sync_handler(self) -> None:
        """Sync handlers work on router."""
        async with InMemoryPubSub() as pubsub:
            marshaler = PydanticMarshaler()
            router = CommandRouter()
            received: list[CreateUser] = []

            @router.handler
            def handle_create_sync(cmd: CreateUser) -> None:
                received.append(cmd)

            bus = CommandBus(pubsub, pubsub, marshaler)
            bus.include_router(router)

            async def send_command() -> None:
                await anyio.sleep(0.01)
                await bus.send(CreateUser(user_id=1, name="Sync"))
                await anyio.sleep(0.02)
                await bus.close()

            with anyio.fail_after(TIMEOUT_SECONDS):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(bus.run)
                    tg.start_soon(send_command)

            assert len(received) == 1
            assert received[0].name == "Sync"

    async def test_multiple_routers(self) -> None:
        """Multiple routers can be included in one bus."""
        async with InMemoryPubSub() as pubsub:
            marshaler = PydanticMarshaler()
            creates: list[CreateUser] = []
            deletes: list[DeleteUser] = []

            router1 = CommandRouter()

            @router1.handler
            async def handle_create(cmd: CreateUser) -> None:
                creates.append(cmd)

            router2 = CommandRouter()

            @router2.handler
            async def handle_delete(cmd: DeleteUser) -> None:
                deletes.append(cmd)

            bus = CommandBus(pubsub, pubsub, marshaler)
            bus.include_router(router1)
            bus.include_router(router2)

            async def send_commands() -> None:
                await anyio.sleep(0.01)
                await bus.send(CreateUser(user_id=1, name="Alice"))
                await bus.send(DeleteUser(user_id=1))
                await anyio.sleep(0.02)
                await bus.close()

            with anyio.fail_after(TIMEOUT_SECONDS):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(bus.run)
                    tg.start_soon(send_commands)

            assert len(creates) == 1
            assert len(deletes) == 1


class TestEventRouter:
    async def test_register_handler(self) -> None:
        """Handler can be registered on a router."""
        router = EventRouter()

        @router.handler
        async def on_user_created(event: UserCreated) -> None:
            pass

        assert UserCreated in router._handlers
        assert on_user_created in router._handlers[UserCreated]

    async def test_include_router_in_bus(self) -> None:
        """Handlers from router are included in bus and receive events."""
        async with InMemoryPubSub() as pubsub:
            marshaler = PydanticMarshaler()
            router = EventRouter()
            received: list[UserCreated] = []

            @router.handler
            async def on_user_created(event: UserCreated) -> None:
                received.append(event)

            bus = EventBus(pubsub, pubsub, marshaler)
            bus.include_router(router)

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
            assert received[0].name == "Alice"

    async def test_include_router_with_prefix(self) -> None:
        """Router prefix is prepended to topic names."""
        async with InMemoryPubSub() as pubsub:
            marshaler = PydanticMarshaler()
            router = EventRouter()
            received: list[UserCreated] = []

            @router.handler
            async def on_user_created(event: UserCreated) -> None:
                received.append(event)

            bus = EventBus(pubsub, pubsub, marshaler)
            bus.include_router(router, prefix="notifications.")

            async def publish_event() -> None:
                await anyio.sleep(0.01)
                await bus.publish(UserCreated(user_id=1, name="Bob"))
                await anyio.sleep(0.02)
                await bus.close()

            with anyio.fail_after(TIMEOUT_SECONDS):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(bus.run)
                    tg.start_soon(publish_event)

            assert len(received) == 1
            assert received[0].name == "Bob"

    async def test_multiple_handlers_same_event(self) -> None:
        """Multiple handlers can be registered for the same event type."""
        router = EventRouter()
        handler1_calls: list[UserCreated] = []
        handler2_calls: list[UserCreated] = []

        @router.handler
        async def handler1(event: UserCreated) -> None:
            handler1_calls.append(event)

        @router.handler
        async def handler2(event: UserCreated) -> None:
            handler2_calls.append(event)

        assert len(router._handlers[UserCreated]) == EXPECTED_HANDLER_COUNT

    async def test_multiple_handlers_receive_events(self) -> None:
        """Multiple handlers for same event all receive the event."""
        async with InMemoryPubSub() as pubsub:
            marshaler = PydanticMarshaler()
            router = EventRouter()
            handler1_received: list[UserCreated] = []
            handler2_received: list[UserCreated] = []

            @router.handler
            async def handler1(event: UserCreated) -> None:
                handler1_received.append(event)

            @router.handler
            async def handler2(event: UserCreated) -> None:
                handler2_received.append(event)

            bus = EventBus(pubsub, pubsub, marshaler)
            bus.include_router(router)

            async def publish_event() -> None:
                await anyio.sleep(0.01)
                await bus.publish(UserCreated(user_id=1, name="Multi"))
                await anyio.sleep(0.05)
                await bus.close()

            with anyio.fail_after(TIMEOUT_SECONDS):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(bus.run)
                    tg.start_soon(publish_event)

            assert len(handler1_received) == 1
            assert len(handler2_received) == 1

    async def test_sync_handler(self) -> None:
        """Sync handlers work on router."""
        async with InMemoryPubSub() as pubsub:
            marshaler = PydanticMarshaler()
            router = EventRouter()
            received: list[UserCreated] = []

            @router.handler
            def on_user_created_sync(event: UserCreated) -> None:
                received.append(event)

            bus = EventBus(pubsub, pubsub, marshaler)
            bus.include_router(router)

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
