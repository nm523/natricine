"""FastAPI chat application using natricine."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, Query
from handlers import command_bus, event_bus, pubsub
from models import JoinRoom, LeaveRoom, MessageSent, SendMessage
from pydantic import BaseModel
from store import chat_store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start and stop the message buses."""
    logger.info("Starting natricine buses...")

    async with pubsub:
        # Run buses in background
        async with asyncio.TaskGroup() as tg:
            tg.create_task(command_bus.run())
            tg.create_task(event_bus.run())

            yield

            # Shutdown
            logger.info("Shutting down natricine buses...")
            await command_bus.close()
            await event_bus.close()


app = FastAPI(title="Natricine Chat Example", lifespan=lifespan)


# Request models
class SendMessageRequest(BaseModel):
    content: str


class JoinRoomRequest(BaseModel):
    username: str


# Endpoints
@app.post("/rooms/{room_id}/messages")
async def send_message(room_id: str, user_id: str, request: SendMessageRequest):
    """Send a message to a room."""
    await command_bus.send(
        SendMessage(room_id=room_id, user_id=user_id, content=request.content)
    )
    return {"status": "sent"}


@app.get("/rooms/{room_id}/messages")
async def get_messages(
    room_id: str,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[MessageSent]:
    """Get recent messages from a room."""
    return chat_store.get_messages(room_id, limit)


@app.post("/rooms/{room_id}/join")
async def join_room(room_id: str, user_id: str, request: JoinRoomRequest):
    """Join a chat room."""
    await command_bus.send(
        JoinRoom(room_id=room_id, user_id=user_id, username=request.username)
    )
    return {"status": "joined"}


@app.post("/rooms/{room_id}/leave")
async def leave_room(room_id: str, user_id: str):
    """Leave a chat room."""
    await command_bus.send(LeaveRoom(room_id=room_id, user_id=user_id))
    return {"status": "left"}


@app.get("/rooms/{room_id}/members")
async def get_members(room_id: str):
    """Get members of a room."""
    return chat_store.get_members(room_id)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
