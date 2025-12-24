# Natricine

**Async-first event-driven architecture toolkit for Python**

A port of [watermill](https://github.com/ThreeDotsLabs/watermill) (Go) to Python, built with modern async patterns and type safety.

## Features

- **Async-first** - Built on `anyio` for true async/await support
- **Type-safe** - Full type hints with Protocol-based abstractions
- **Pluggable backends** - In-memory, Redis Streams, AWS SQS/SNS, PostgreSQL, SQLite
- **CQRS support** - CommandBus and EventBus with Pydantic marshaling
- **Middleware** - Retry, timeout, dead-letter queues, OpenTelemetry tracing
- **FastAPI integration** - Depends-style dependency injection

## Quick Example

```python
import asyncio
from natricine.pubsub import InMemoryPubSub, Message
from natricine.cqrs import CommandBus, EventBus, PydanticMarshaler
from pydantic import BaseModel

class CreateUser(BaseModel):
    user_id: str
    name: str

class UserCreated(BaseModel):
    user_id: str
    name: str

pubsub = InMemoryPubSub()
marshaler = PydanticMarshaler()
command_bus = CommandBus(pubsub, pubsub, marshaler)
event_bus = EventBus(pubsub, pubsub, marshaler)

@command_bus.handler
async def handle_create_user(cmd: CreateUser) -> None:
    print(f"Creating user: {cmd.name}")
    await event_bus.publish(UserCreated(user_id=cmd.user_id, name=cmd.name))

@event_bus.handler
async def on_user_created(event: UserCreated) -> None:
    print(f"User created: {event.name}")

async def main():
    async with pubsub:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(command_bus.run())
            tg.create_task(event_bus.run())

            await command_bus.send(CreateUser(user_id="1", name="Alice"))
            await asyncio.sleep(0.1)

            await command_bus.close()
            await event_bus.close()

asyncio.run(main())
```

## Package Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        natricine                             │  ← Core package
│  pubsub: Message, Publisher, Subscriber, InMemoryPubSub      │
│  router: Router, Middleware                                  │
│  cqrs: CommandBus, EventBus                                  │
└──────────────────────────────────────────────────────────────┘

Backends:
┌──────────────────┐ ┌───────────────┐ ┌────────────────┐
│natricine-redis   │ │ natricine-aws │ │ natricine-sql  │
│Redis Streams     │ │ SQS/SNS       │ │ Postgres/SQLite│
└──────────────────┘ └───────────────┘ └────────────────┘
┌──────────────────┐
│natricine-http    │
│HTTP webhooks     │
└──────────────────┘

Monitoring:
┌───────────────┐
│ natricine-otel│
│ OpenTelemetry │
└───────────────┘
```

## Next Steps

- [Installation](getting-started/installation.md) - Get natricine installed
- [Quick Start](getting-started/quickstart.md) - Build your first event-driven app
- [Core Concepts](concepts/messages.md) - Understand the architecture
