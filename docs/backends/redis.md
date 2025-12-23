# Redis Streams

Redis Streams backend for production workloads with low latency.

## Installation

```bash
pip install natricine-redisstream
```

## Usage

```python
from redis.asyncio import Redis
from natricine.redisstream import RedisStreamPublisher, RedisStreamSubscriber
from natricine.pubsub import Message

redis = Redis.from_url("redis://localhost:6379")

publisher = RedisStreamPublisher(redis)
subscriber = RedisStreamSubscriber(
    redis,
    group_name="my-service",
    consumer_name="worker-1",
)

# Publish
await publisher.publish("orders", Message(payload=b'{"id": 1}'))

# Subscribe (consumer group ensures each message processed once)
async for msg in subscriber.subscribe("orders"):
    print(f"Received: {msg.payload}")
    await msg.ack()  # XACK to Redis
```

## Configuration

```python
RedisStreamSubscriber(
    redis,
    group_name="my-service",    # Consumer group name
    consumer_name="worker-1",    # Unique consumer identifier
    block_ms=5000,               # Block time waiting for messages
    count=10,                    # Max messages per batch
)
```

## Consumer Groups

Redis Streams consumer groups provide:

- **Competing consumers**: Messages distributed across workers
- **At-least-once delivery**: Unacked messages redelivered
- **Message tracking**: Redis tracks pending messages

```python
# Multiple workers in same group share the load
worker1 = RedisStreamSubscriber(redis, "processors", "worker-1")
worker2 = RedisStreamSubscriber(redis, "processors", "worker-2")
# Message goes to worker1 OR worker2, not both

# Different groups each get all messages
analytics = RedisStreamSubscriber(redis, "analytics", "worker-1")
notifications = RedisStreamSubscriber(redis, "notifications", "worker-1")
# Same message goes to both groups
```

## Characteristics

| Feature | Behavior |
|---------|----------|
| Delivery | At-least-once |
| Pattern | Competing consumers (within group) |
| Persistence | Yes (Redis persistence) |
| Ordering | FIFO within stream |

## With CQRS

```python
from natricine.cqrs import CommandBus, PydanticMarshaler

marshaler = PydanticMarshaler()
command_bus = CommandBus(
    publisher=RedisStreamPublisher(redis),
    subscriber=RedisStreamSubscriber(redis, "commands", "worker-1"),
    marshaler=marshaler,
)

@command_bus.handler
async def handle_create_user(cmd: CreateUser) -> None:
    ...
```

## Production Setup

```python
import os
from redis.asyncio import Redis

redis = Redis.from_url(
    os.environ["REDIS_URL"],
    decode_responses=False,  # Keep binary for payloads
)

# Multiple workers
import socket
consumer_name = f"{socket.gethostname()}-{os.getpid()}"

subscriber = RedisStreamSubscriber(
    redis,
    group_name="order-service",
    consumer_name=consumer_name,
    block_ms=5000,
    count=10,
)
```

## Error Handling

```python
async for msg in subscriber.subscribe("orders"):
    try:
        await process(msg)
        await msg.ack()
    except Exception:
        await msg.nack()  # Message stays pending for redelivery
```

Unacked messages are redelivered to other consumers in the group.
