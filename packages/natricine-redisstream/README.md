# natricine-redisstream

Redis Streams pub/sub implementation.

## Installation

```bash
pip install natricine-redisstream
```

## Usage

```python
import asyncio
from redis.asyncio import Redis
from natricine.pubsub import Message
from natricine.backends.redis import RedisStreamPublisher, RedisStreamSubscriber

async def main():
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
        await msg.ack()  # Acknowledges to Redis
        break

    await redis.aclose()

asyncio.run(main())
```

## Consumer Groups

Redis Streams consumer groups provide:
- **Competing consumers**: Messages distributed across workers in same group
- **At-least-once delivery**: Unacked messages redelivered after visibility timeout
- **Message tracking**: Redis tracks pending messages per consumer

```python
# Multiple workers in same group share the load
subscriber1 = RedisStreamSubscriber(redis, "order-processors", "worker-1")
subscriber2 = RedisStreamSubscriber(redis, "order-processors", "worker-2")

# Different groups each get all messages (fan-out)
analytics = RedisStreamSubscriber(redis, "analytics", "worker-1")
notifications = RedisStreamSubscriber(redis, "notifications", "worker-1")
```

## Configuration

```python
RedisStreamSubscriber(
    redis,
    group_name="my-service",
    consumer_name="worker-1",
    block_ms=5000,  # Block time waiting for messages (default: 5000)
    count=10,       # Max messages per batch (default: 10)
)
```

## With CQRS

```python
from natricine.cqrs import CommandBus, PydanticMarshaler

marshaler = PydanticMarshaler()
command_bus = CommandBus(
    publisher=RedisStreamPublisher(redis),
    subscriber=RedisStreamSubscriber(redis, "commands", "worker-1"),
    marshaler=marshaler,
)
```
