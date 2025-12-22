# Natricine Chat Example

A simple chat application demonstrating natricine's CQRS pattern with FastAPI.

## Architecture

```
Commands              Events                 Handlers
---------             ------                 --------
SendMessage   ->      MessageSent    ->      log_message_sent
JoinRoom      ->      UserJoined     ->      log_user_joined
LeaveRoom     ->      UserLeft       ->      log_user_left
```

## Features

- **Commands**: `SendMessage`, `JoinRoom`, `LeaveRoom`
- **Events**: `MessageSent`, `UserJoined`, `UserLeft`
- **Dependency Injection**:
  - `ChatStore` injected via natricine's `Depends`
  - `CommandBus`/`EventBus` injected via FastAPI's `Depends`
- **FastAPI Integration**: REST endpoints that dispatch commands

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

## Code Structure

```
src/chat_example/
  __init__.py      - Package init
  models.py        - Pydantic models for commands and events
  store.py         - In-memory chat storage
  dependencies.py  - FastAPI dependency providers (buses, store)
  handlers.py      - Command and event handlers
  app.py           - FastAPI application with lifespan management
```
