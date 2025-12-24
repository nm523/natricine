# CQRS

Command Query Responsibility Segregation (CQRS) separates read and write operations. Natricine provides `CommandBus` and `EventBus` for this pattern. [Watermill](https://watermill.io/docs/cqrs/) provides an excellent overview and components for handling this behaviour.

## Setup

```python
from natricine.pubsub import InMemoryPubSub
from natricine.cqrs import CommandBus, EventBus, PydanticMarshaler
from pydantic import BaseModel

pubsub = InMemoryPubSub()
marshaler = PydanticMarshaler()

command_bus = CommandBus(pubsub, pubsub, marshaler)
event_bus = EventBus(pubsub, pubsub, marshaler)
```

## Defining Commands and Events

Use Pydantic models for type-safe serialization:

```python
from pydantic import BaseModel

# Commands - imperative
class CreateUser(BaseModel):
    user_id: str
    email: str
    name: str

class DeleteUser(BaseModel):
    user_id: str

# Events - past tense
class UserCreated(BaseModel):
    user_id: str
    email: str
    name: str
    created_at: datetime

class UserDeleted(BaseModel):
    user_id: str
    deleted_at: datetime
```

## Command Handlers

Each command type has **exactly one** handler:

```python
@command_bus.handler
async def handle_create_user(cmd: CreateUser) -> None:
    # Process the command
    user = await db.create_user(cmd.user_id, cmd.email, cmd.name)

    # Publish resulting event
    await event_bus.publish(UserCreated(
        user_id=user.id,
        email=user.email,
        name=user.name,
        created_at=user.created_at,
    ))

@command_bus.handler
async def handle_delete_user(cmd: DeleteUser) -> None:
    await db.delete_user(cmd.user_id)
    await event_bus.publish(UserDeleted(
        user_id=cmd.user_id,
        deleted_at=datetime.now(),
    ))
```

## Event Handlers

Events can have **multiple** handlers (or none):

```python
@event_bus.handler
async def send_welcome_email(event: UserCreated) -> None:
    await email.send_welcome(event.email, event.name)

@event_bus.handler
async def update_analytics(event: UserCreated) -> None:
    await analytics.track("user_created", event.user_id)

@event_bus.handler
async def notify_admin(event: UserCreated) -> None:
    await slack.notify(f"New user: {event.name}")
```

## Sending Commands

```python
await command_bus.send(CreateUser(
    user_id="user-123",
    email="alice@example.com",
    name="Alice",
))
```

## Publishing Events

```python
await event_bus.publish(UserCreated(
    user_id="user-123",
    email="alice@example.com",
    name="Alice",
    created_at=datetime.now(),
))
```

## Running the Buses

```python
async def main():
    async with pubsub:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(command_bus.run())
            tg.create_task(event_bus.run())

            # Your application logic
            await command_bus.send(CreateUser(...))

            # Graceful shutdown
            await command_bus.close()
            await event_bus.close()
```

## Dependency Injection

Use `Depends` for injecting services into handlers:

```python
from typing import Annotated
from natricine.cqrs import Depends

async def get_db() -> Database:
    return Database()

@command_bus.handler
async def handle_create_user(
    cmd: CreateUser,
    db: Annotated[Database, Depends(get_db)],
) -> None:
    await db.create_user(cmd.user_id, cmd.email)
```

## Routers for Modular Code

Organize handlers in separate modules:

```python
# users/handlers.py
from natricine.cqrs import CommandRouter

router = CommandRouter()

@router.handler
async def handle_create_user(cmd: CreateUser) -> None:
    ...

# main.py
command_bus.include_router(router, prefix="users.")
```

## Topic Naming

By default, topics are derived from the model class name:

- `CreateUser` → `command.CreateUser`
- `UserCreated` → `event.UserCreated`

Customize with `topic_prefix`:

```python
command_bus = CommandBus(..., topic_prefix="myapp.commands.")
# CreateUser → myapp.commands.CreateUser
```
