"""Chat domain models - commands and events."""

from datetime import datetime

from pydantic import BaseModel, Field


# Commands
class SendMessage(BaseModel):
    """Command to send a message to a room."""

    room_id: str
    user_id: str
    content: str


class JoinRoom(BaseModel):
    """Command to join a chat room."""

    room_id: str
    user_id: str
    username: str


class LeaveRoom(BaseModel):
    """Command to leave a chat room."""

    room_id: str
    user_id: str


# Events
class MessageSent(BaseModel):
    """Event emitted when a message is sent."""

    room_id: str
    user_id: str
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)


class UserJoined(BaseModel):
    """Event emitted when a user joins a room."""

    room_id: str
    user_id: str
    username: str
    timestamp: datetime = Field(default_factory=datetime.now)


class UserLeft(BaseModel):
    """Event emitted when a user leaves a room."""

    room_id: str
    user_id: str
    timestamp: datetime = Field(default_factory=datetime.now)
