"""Tests for CommandBus."""

from typing import Annotated

import anyio
import pytest
from pydantic import BaseModel

from natricine.cqrs import CommandBus, Depends, PydanticMarshaler
from natricine.pubsub import InMemoryPubSub

pytestmark = pytest.mark.anyio

TIMEOUT_SECONDS = 2


class CreateUser(BaseModel):
    user_id: int
    name: str


class DeleteUser(BaseModel):
    user_id: int


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

    async def test_handler_without_type_hint_raises(self) -> None:
        async with InMemoryPubSub() as pubsub:
            marshaler = PydanticMarshaler()
            bus = CommandBus(pubsub, pubsub, marshaler)

            with pytest.raises(TypeError, match="must be typed"):

                @bus.handler
                async def bad_handler(cmd) -> None:  # noqa: ANN001
                    pass
