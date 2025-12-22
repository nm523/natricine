"""FastAPI chat application using natricine."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Query
from pydantic import BaseModel

from chat_example import handlers  # noqa: F401 - registers handlers
from chat_example.dependencies import (
    get_chat_store,
    get_command_bus,
    get_event_bus,
    get_pubsub,
)
from chat_example.models import JoinRoom, LeaveRoom, MessageSent, SendMessage
from chat_example.store import ChatStore
from natricine.cqrs import CommandBus, EventBus
from natricine.pubsub import InMemoryPubSub

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start and stop the message buses."""
    logger.info("Starting natricine buses...")

    pubsub = get_pubsub()
    command_bus = get_command_bus()
    event_bus = get_event_bus()

    async with pubsub:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(command_bus.run())
            tg.create_task(event_bus.run())

            yield

            logger.info("Shutting down natricine buses...")
            await command_bus.close()
            await event_bus.close()


app = FastAPI(title="Natricine Chat Example", lifespan=lifespan)


# Request models
class SendMessageRequest(BaseModel):
    content: str


class JoinRoomRequest(BaseModel):
    username: str


# Type aliases for FastAPI dependencies
CommandBusDep = Annotated[CommandBus, Depends(get_command_bus)]
EventBusDep = Annotated[EventBus, Depends(get_event_bus)]
PubSubDep = Annotated[InMemoryPubSub, Depends(get_pubsub)]
ChatStoreDep = Annotated[ChatStore, Depends(get_chat_store)]


# Endpoints
@app.post("/rooms/{room_id}/messages")
async def send_message(
    room_id: str,
    user_id: str,
    request: SendMessageRequest,
    command_bus: CommandBusDep,
):
    """Send a message to a room."""
    await command_bus.send(
        SendMessage(room_id=room_id, user_id=user_id, content=request.content)
    )
    return {"status": "sent"}


@app.get("/rooms/{room_id}/messages")
async def get_messages(
    room_id: str,
    store: ChatStoreDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[MessageSent]:
    """Get recent messages from a room."""
    return store.get_messages(room_id, limit)


@app.post("/rooms/{room_id}/join")
async def join_room(
    room_id: str,
    user_id: str,
    request: JoinRoomRequest,
    command_bus: CommandBusDep,
):
    """Join a chat room."""
    await command_bus.send(
        JoinRoom(room_id=room_id, user_id=user_id, username=request.username)
    )
    return {"status": "joined"}


@app.post("/rooms/{room_id}/leave")
async def leave_room(
    room_id: str,
    user_id: str,
    command_bus: CommandBusDep,
):
    """Leave a chat room."""
    await command_bus.send(LeaveRoom(room_id=room_id, user_id=user_id))
    return {"status": "left"}


@app.get("/rooms/{room_id}/members")
async def get_members(room_id: str, store: ChatStoreDep):
    """Get members of a room."""
    return store.get_members(room_id)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
