"""Tests for CommandBus."""

from typing import Annotated

import anyio
import pytest
from pydantic import BaseModel

from natricine.cqrs import CommandBus, Depends, PydanticMarshaler
from natricine.pubsub import InMemoryPubSub, Subscriber

pytestmark = pytest.mark.anyio

TIMEOUT_SECONDS = 2


class CreateUser(BaseModel):
    user_id: int
    name: str


class DeleteUser(BaseModel):
    user_id: int


class UpdateUser(BaseModel):
    user_id: int
    name: str


class TestCommandBus:
    async def test_command_routed_to_handler(self) -> None:
        async with InMemoryPubSub() as pubsub:
            marshaler = PydanticMarshaler()
            bus = CommandBus(pubsub, pubsub, marshaler)
            received: list[CreateUser] = []

            @bus.handler
            async def handle_create(cmd: CreateUser) -> None:
                received.append(cmd)

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
            assert received[0].user_id == 1
            assert received[0].name == "Alice"

    async def test_multiple_command_types(self) -> None:
        async with InMemoryPubSub() as pubsub:
            marshaler = PydanticMarshaler()
            bus = CommandBus(pubsub, pubsub, marshaler)
            creates: list[CreateUser] = []
            deletes: list[DeleteUser] = []

            @bus.handler
            async def handle_create(cmd: CreateUser) -> None:
                creates.append(cmd)

            @bus.handler
            async def handle_delete(cmd: DeleteUser) -> None:
                deletes.append(cmd)

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

    async def test_handler_with_depends(self) -> None:
        async with InMemoryPubSub() as pubsub:
            marshaler = PydanticMarshaler()
            bus = CommandBus(pubsub, pubsub, marshaler)
            results: list[tuple[CreateUser, str]] = []

            def get_service() -> str:
                return "injected_service"

            @bus.handler
            async def handle_create(
                cmd: CreateUser,
                service: Annotated[str, Depends(get_service)],
            ) -> None:
                results.append((cmd, service))

            async def send_command() -> None:
                await anyio.sleep(0.01)
                await bus.send(CreateUser(user_id=1, name="Test"))
                await anyio.sleep(0.02)
                await bus.close()

            with anyio.fail_after(TIMEOUT_SECONDS):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(bus.run)
                    tg.start_soon(send_command)

            assert len(results) == 1
            assert results[0][0].name == "Test"
            assert results[0][1] == "injected_service"

    async def test_sync_handler(self) -> None:
        async with InMemoryPubSub() as pubsub:
            marshaler = PydanticMarshaler()
            bus = CommandBus(pubsub, pubsub, marshaler)
            received: list[CreateUser] = []

            @bus.handler
            def handle_create_sync(cmd: CreateUser) -> None:
                received.append(cmd)

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

    async def test_sync_handler_with_depends(self) -> None:
        async with InMemoryPubSub() as pubsub:
            marshaler = PydanticMarshaler()
            bus = CommandBus(pubsub, pubsub, marshaler)
            results: list[tuple[CreateUser, str]] = []

            def get_service() -> str:
                return "sync_service"

            @bus.handler
            def handle_create_sync(
                cmd: CreateUser,
                service: Annotated[str, Depends(get_service)],
            ) -> None:
                results.append((cmd, service))

            async def send_command() -> None:
                await anyio.sleep(0.01)
                await bus.send(CreateUser(user_id=1, name="SyncDI"))
                await anyio.sleep(0.02)
                await bus.close()

            with anyio.fail_after(TIMEOUT_SECONDS):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(bus.run)
                    tg.start_soon(send_command)

            assert len(results) == 1
            assert results[0][0].name == "SyncDI"
            assert results[0][1] == "sync_service"

    async def test_handler_without_type_hint_raises(self) -> None:
        async with InMemoryPubSub() as pubsub:
            marshaler = PydanticMarshaler()
            bus = CommandBus(pubsub, pubsub, marshaler)

            with pytest.raises(TypeError, match="must be typed"):

                @bus.handler
                async def bad_handler(cmd) -> None:  # noqa: ANN001
                    pass


class TestCommandBusSubscriberFactory:
    """Tests for subscriber_factory pattern."""

    async def test_factory_creates_subscriber_per_handler(self) -> None:
        """Test that subscriber_factory is called for each handler."""
        async with InMemoryPubSub() as pubsub:
            marshaler = PydanticMarshaler()
            created_subscribers: list[str] = []

            def subscriber_factory(handler_name: str) -> Subscriber:
                created_subscribers.append(handler_name)
                return pubsub

            bus = CommandBus(
                pubsub,
                marshaler=marshaler,
                subscriber_factory=subscriber_factory,
            )
            received_create: list[CreateUser] = []
            received_delete: list[DeleteUser] = []

            @bus.handler
            async def handle_create(cmd: CreateUser) -> None:
                received_create.append(cmd)

            @bus.handler
            async def handle_delete(cmd: DeleteUser) -> None:
                received_delete.append(cmd)

            async def send_and_close() -> None:
                await anyio.sleep(0.01)
                await bus.send(CreateUser(user_id=1, name="Test"))
                await bus.send(DeleteUser(user_id=1))
                await anyio.sleep(0.05)
                await bus.close()

            with anyio.fail_after(TIMEOUT_SECONDS):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(bus.run)
                    tg.start_soon(send_and_close)

            # Factory should have been called for each handler
            expected_handlers = {"handle_create", "handle_delete"}
            assert set(created_subscribers) == expected_handlers

    async def test_validation_requires_subscriber_or_factory(self) -> None:
        """Test that either subscriber or subscriber_factory is required."""
        async with InMemoryPubSub() as pubsub:
            marshaler = PydanticMarshaler()

            with pytest.raises(ValueError, match="Must provide either"):
                CommandBus(pubsub, marshaler=marshaler)


class TestCommandBusGenerateTopic:
    """Tests for generate_topic custom topic generation."""

    async def test_generate_topic_overrides_default(self) -> None:
        """Test that generate_topic callback overrides default naming."""
        async with InMemoryPubSub() as pubsub:
            marshaler = PydanticMarshaler()
            generated_topics: list[str] = []

            def custom_topic_gen(command_name: str) -> str:
                topic = f"custom.{command_name.lower()}"
                generated_topics.append(topic)
                return topic

            bus = CommandBus(
                pubsub,
                pubsub,
                marshaler=marshaler,
                generate_topic=custom_topic_gen,
            )
            received: list[CreateUser] = []

            @bus.handler
            async def handle_create(cmd: CreateUser) -> None:
                received.append(cmd)

            async def send_and_close() -> None:
                await anyio.sleep(0.01)
                await bus.send(CreateUser(user_id=1, name="Test"))
                await anyio.sleep(0.02)
                await bus.close()

            with anyio.fail_after(TIMEOUT_SECONDS):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(bus.run)
                    tg.start_soon(send_and_close)

            # Custom topic generator should have been used
            assert "custom.createuser" in generated_topics
            assert len(received) == 1
