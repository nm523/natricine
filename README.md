# natricine

Python port of [watermill](https://github.com/ThreeDotsLabs/watermill). Async-first event-driven architecture toolkit. "Vibe ported" with Opus 4.5, as such there are no guarantees at this stage of compatibility.

## Installation

```bash
pip install natricine

# Backends
pip install natricine-redisstream    # Redis Streams
pip install natricine-aws            # AWS SNS/SQS
pip install natricine-sql            # PostgreSQL/SQLite
pip install natricine-http           # HTTP webhooks
pip install natricine_otel           # OpenTelemetry tracing/metrics
```

## Quick Start

```python
import asyncio
from natricine.pubsub import InMemoryPubSub, Message
from natricine.cqrs import CommandBus, EventBus, PydanticMarshaler
from pydantic import BaseModel

# Define commands and events
class CreateUser(BaseModel):
    user_id: str
    name: str

class UserCreated(BaseModel):
    user_id: str
    name: str

# Set up buses
pubsub = InMemoryPubSub()
marshaler = PydanticMarshaler()
command_bus = CommandBus(pubsub, pubsub, marshaler)
event_bus = EventBus(pubsub, pubsub, marshaler)

# Register handlers
@command_bus.handler
async def handle_create_user(cmd: CreateUser) -> None:
    print(f"Creating user: {cmd.name}")
    await event_bus.publish(UserCreated(user_id=cmd.user_id, name=cmd.name))

@event_bus.handler
async def on_user_created(event: UserCreated) -> None:
    print(f"User created: {event.name}")

# Run
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

## Package Structure

```
natricine                     # Core package
├── pubsub                    # Message, Publisher, Subscriber, InMemoryPubSub
├── router                    # Router, Middleware
└── cqrs                      # CommandBus, EventBus

natricine_redis               # pip install natricine-redisstream
natricine_aws                 # pip install natricine-aws
natricine_sql                 # pip install natricine-sql
natricine_http                # pip install natricine-http
natricine_otel                # pip install natricine_otel
```

## Backends

### In-Memory (built-in)

```python
from natricine.pubsub import InMemoryPubSub

pubsub = InMemoryPubSub()
```

### Redis Streams

```python
from redis.asyncio import Redis
from natricine_redis import RedisStreamPublisher, RedisStreamSubscriber

redis = Redis.from_url("redis://localhost:6379")
publisher = RedisStreamPublisher(redis)
subscriber = RedisStreamSubscriber(redis, group_name="my-app", consumer_name="worker-1")
```

### AWS SQS/SNS

```python
import aioboto3
from natricine_aws import SQSPublisher, SQSSubscriber, SNSPublisher, SNSSubscriber, SNSConfig

session = aioboto3.Session()

# Direct SQS
publisher = SQSPublisher(session)
subscriber = SQSSubscriber(session)

# SNS fan-out to SQS
sns_publisher = SNSPublisher(session)
sns_subscriber = SNSSubscriber(session, config=SNSConfig(consumer_group="my-group"))
```

## Middleware

```python
from natricine.router import Router, retry, timeout

router = Router()
router.add_middleware(retry(max_retries=3, delay=1.0))
router.add_middleware(timeout(seconds=30))
```

## References

- [watermill](https://github.com/ThreeDotsLabs/watermill) - Go event-driven library (inspiration)
- [watermill-aws](https://github.com/ThreeDotsLabs/watermill-aws) - AWS backend reference
