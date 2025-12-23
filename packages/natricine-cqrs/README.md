# natricine-cqrs

CQRS pattern with CommandBus and EventBus.

Part of the `natricine` package - install via `pip install natricine`.

## Usage

```python
import asyncio
from pydantic import BaseModel
from natricine.pubsub import InMemoryPubSub
from natricine.cqrs import CommandBus, EventBus, PydanticMarshaler

# Define commands and events
class CreateUser(BaseModel):
    email: str

class UserCreated(BaseModel):
    user_id: str
    email: str

async def main():
    async with InMemoryPubSub() as pubsub:
        marshaler = PydanticMarshaler()

        # Command bus - one handler per command type
        command_bus = CommandBus(pubsub, pubsub, marshaler)

        @command_bus.handler
        async def handle_create_user(cmd: CreateUser) -> None:
            print(f"Creating user: {cmd.email}")
            # Publish event after handling command
            await event_bus.publish(UserCreated(user_id="123", email=cmd.email))

        # Event bus - multiple handlers per event type
        event_bus = EventBus(pubsub, pubsub, marshaler)

        @event_bus.handler
        async def send_welcome_email(event: UserCreated) -> None:
            print(f"Welcome email to {event.email}")

        @event_bus.handler
        async def update_analytics(event: UserCreated) -> None:
            print(f"Analytics: new user {event.user_id}")

        # Run buses and send command
        async with asyncio.TaskGroup() as tg:
            tg.create_task(command_bus.run())
            tg.create_task(event_bus.run())

            await asyncio.sleep(0.1)  # Wait for subscriptions
            await command_bus.send(CreateUser(email="user@example.com"))
            await asyncio.sleep(0.1)  # Wait for processing

            await command_bus.close()
            await event_bus.close()

asyncio.run(main())
```

## Routers (Deferred Registration)

Register handlers before creating the bus:

```python
from natricine.cqrs import CommandRouter, EventRouter

# In handlers.py
router = CommandRouter()

@router.handler
async def handle_create_user(cmd: CreateUser) -> None:
    ...

# In main.py
command_bus = CommandBus(publisher, subscriber, marshaler)
command_bus.include_router(router, prefix="users.")
```

## Dependency Injection

```python
from typing import Annotated
from natricine.cqrs import Depends

def get_db() -> Database:
    return Database()

@command_bus.handler
async def handle_create_user(
    cmd: CreateUser,
    db: Annotated[Database, Depends(get_db)],
) -> None:
    await db.insert_user(cmd.email)
```

## Marshaler

Converts between typed objects and `Message`:

```python
from natricine.cqrs import PydanticMarshaler, Marshaler

# Built-in Pydantic support
marshaler = PydanticMarshaler()

# Custom marshaler
class MyMarshaler(Marshaler):
    def marshal(self, obj: object) -> Message: ...
    def unmarshal(self, message: Message, cls: type[T]) -> T: ...
    def name(self, cls: type) -> str: ...
```
