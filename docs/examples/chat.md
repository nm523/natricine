# Chat Application

A FastAPI chat application demonstrating CQRS with natricine.

## Overview

This example shows:

- Command/event separation with Pydantic models
- Dependency injection with `Depends`
- FastAPI integration
- In-memory pub/sub for simplicity

## Architecture

```
Commands              Events                 Handlers
---------             ------                 --------
SendMessage   ->      MessageSent    ->      log_message_sent
JoinRoom      ->      UserJoined     ->      log_user_joined
LeaveRoom     ->      UserLeft       ->      log_user_left
```

## Models

Commands and events are Pydantic models:

```python
from pydantic import BaseModel, Field
from datetime import datetime

# Commands
class SendMessage(BaseModel):
    room_id: str
    user_id: str
    content: str

class JoinRoom(BaseModel):
    room_id: str
    user_id: str
    username: str

class LeaveRoom(BaseModel):
    room_id: str
    user_id: str

# Events
class MessageSent(BaseModel):
    room_id: str
    user_id: str
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)

class UserJoined(BaseModel):
    room_id: str
    user_id: str
    username: str
    timestamp: datetime = Field(default_factory=datetime.now)

class UserLeft(BaseModel):
    room_id: str
    user_id: str
    timestamp: datetime = Field(default_factory=datetime.now)
```

## Handlers

Handlers use `Depends` for dependency injection:

```python
from typing import Annotated
from natricine.cqrs import Depends

@command_bus.handler
async def handle_send_message(
    cmd: SendMessage,
    store: Annotated[ChatStore, Depends(get_chat_store)],
) -> None:
    event = MessageSent(
        room_id=cmd.room_id,
        user_id=cmd.user_id,
        content=cmd.content,
    )
    store.add_message(event)
    await event_bus.publish(event)

@event_bus.handler
async def log_message_sent(event: MessageSent) -> None:
    logger.info("[%s] %s: %s", event.room_id, event.user_id, event.content)
```

## Running

```bash
cd examples/chat
uv sync
uv run python -m chat_example.app
```

## API

```bash
# Join a room
curl -X POST "http://localhost:8000/rooms/general/join?user_id=alice" \
  -H "Content-Type: application/json" \
  -d '{"username": "Alice"}'

# Send a message
curl -X POST "http://localhost:8000/rooms/general/messages?user_id=alice" \
  -H "Content-Type: application/json" \
  -d '{"content": "Hello, world!"}'

# Get messages
curl "http://localhost:8000/rooms/general/messages"

# Get room members
curl "http://localhost:8000/rooms/general/members"

# Leave room
curl -X POST "http://localhost:8000/rooms/general/leave?user_id=alice"
```

## File Structure

```
examples/chat/
  src/chat_example/
    __init__.py      - Package init
    models.py        - Pydantic models for commands and events
    store.py         - In-memory chat storage
    dependencies.py  - FastAPI dependency providers
    handlers.py      - Command and event handlers
    app.py           - FastAPI application
```

## Key Patterns

### Dependency Injection

natricine's `Depends` mirrors FastAPI's pattern:

```python
async def handle_command(
    cmd: MyCommand,
    service: Annotated[MyService, Depends(get_service)],
) -> None:
    await service.do_work(cmd)
```

### Event Publishing

Commands trigger events for side effects:

```python
@command_bus.handler
async def handle_join(cmd: JoinRoom, store: ...) -> None:
    store.add_member(cmd.room_id, cmd.user_id, cmd.username)
    await event_bus.publish(UserJoined(...))
```

### Multiple Event Handlers

Events can have multiple handlers:

```python
@event_bus.handler
async def log_message(event: MessageSent) -> None:
    logger.info("Message sent: %s", event.content)

@event_bus.handler
async def notify_users(event: MessageSent) -> None:
    await push_notification(event)
```
