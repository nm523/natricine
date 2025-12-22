"""Simple in-memory chat store."""

from dataclasses import dataclass, field

from models import MessageSent, UserJoined


@dataclass
class RoomState:
    """State of a chat room."""

    members: dict[str, str] = field(default_factory=dict)  # user_id -> username
    messages: list[MessageSent] = field(default_factory=list)


class ChatStore:
    """In-memory store for chat rooms."""

    def __init__(self) -> None:
        self._rooms: dict[str, RoomState] = {}

    def get_or_create_room(self, room_id: str) -> RoomState:
        if room_id not in self._rooms:
            self._rooms[room_id] = RoomState()
        return self._rooms[room_id]

    def add_member(self, room_id: str, user_id: str, username: str) -> None:
        room = self.get_or_create_room(room_id)
        room.members[user_id] = username

    def remove_member(self, room_id: str, user_id: str) -> None:
        room = self.get_or_create_room(room_id)
        room.members.pop(user_id, None)

    def add_message(self, event: MessageSent) -> None:
        room = self.get_or_create_room(event.room_id)
        room.messages.append(event)

    def get_messages(self, room_id: str, limit: int = 50) -> list[MessageSent]:
        room = self.get_or_create_room(room_id)
        return room.messages[-limit:]

    def get_members(self, room_id: str) -> list[UserJoined]:
        room = self.get_or_create_room(room_id)
        return [
            UserJoined(room_id=room_id, user_id=uid, username=name)
            for uid, name in room.members.items()
        ]


# Global store instance
chat_store = ChatStore()


def get_chat_store() -> ChatStore:
    """Dependency provider for ChatStore."""
    return chat_store
