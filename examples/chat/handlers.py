"""Command and event handlers for the chat system."""

import logging
from typing import Annotated

from models import (
    JoinRoom,
    LeaveRoom,
    MessageSent,
    SendMessage,
    UserJoined,
    UserLeft,
)
from store import ChatStore, get_chat_store

from natricine.cqrs import CommandBus, Depends, EventBus, PydanticMarshaler
from natricine.pubsub import InMemoryPubSub

logger = logging.getLogger(__name__)

# Shared pubsub and marshaler
pubsub = InMemoryPubSub()
marshaler = PydanticMarshaler()

# Create buses
command_bus = CommandBus(pubsub, pubsub, marshaler)
event_bus = EventBus(pubsub, pubsub, marshaler)


# Command handlers
@command_bus.handler
async def handle_send_message(
    cmd: SendMessage,
    store: Annotated[ChatStore, Depends(get_chat_store)],
) -> None:
    """Handle SendMessage command by publishing MessageSent event."""
    logger.info("User %s sending message to room %s", cmd.user_id, cmd.room_id)

    event = MessageSent(
        room_id=cmd.room_id,
        user_id=cmd.user_id,
        content=cmd.content,
    )
    store.add_message(event)
    await event_bus.publish(event)


@command_bus.handler
async def handle_join_room(
    cmd: JoinRoom,
    store: Annotated[ChatStore, Depends(get_chat_store)],
) -> None:
    """Handle JoinRoom command by publishing UserJoined event."""
    logger.info("User %s joining room %s", cmd.user_id, cmd.room_id)

    store.add_member(cmd.room_id, cmd.user_id, cmd.username)

    event = UserJoined(
        room_id=cmd.room_id,
        user_id=cmd.user_id,
        username=cmd.username,
    )
    await event_bus.publish(event)


@command_bus.handler
async def handle_leave_room(
    cmd: LeaveRoom,
    store: Annotated[ChatStore, Depends(get_chat_store)],
) -> None:
    """Handle LeaveRoom command by publishing UserLeft event."""
    logger.info("User %s leaving room %s", cmd.user_id, cmd.room_id)

    store.remove_member(cmd.room_id, cmd.user_id)

    event = UserLeft(room_id=cmd.room_id, user_id=cmd.user_id)
    await event_bus.publish(event)


# Event handlers (for logging, notifications, etc.)
@event_bus.handler
async def log_message_sent(event: MessageSent) -> None:
    """Log when a message is sent."""
    logger.info(
        "[%s] %s: %s",
        event.room_id,
        event.user_id,
        event.content,
    )


@event_bus.handler
async def log_user_joined(event: UserJoined) -> None:
    """Log when a user joins."""
    logger.info(
        "[%s] %s joined the room",
        event.room_id,
        event.username,
    )


@event_bus.handler
async def log_user_left(event: UserLeft) -> None:
    """Log when a user leaves."""
    logger.info(
        "[%s] User %s left the room",
        event.room_id,
        event.user_id,
    )
