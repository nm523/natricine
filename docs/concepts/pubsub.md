# Publishers & Subscribers

Natricine uses Protocol-based abstractions for publishers and subscribers, allowing any backend to implement the same interface.

## Publisher Protocol

```python
from typing import Protocol
from natricine.pubsub import Message

class Publisher(Protocol):
    async def publish(self, topic: str, *messages: Message) -> None:
        """Publish one or more messages to a topic."""
        ...

    async def close(self) -> None:
        """Close the publisher and release resources."""
        ...

    async def __aenter__(self) -> "Publisher":
        ...

    async def __aexit__(self, *args) -> None:
        ...
```

### Usage

```python
from natricine.pubsub import InMemoryPubSub, Message

pubsub = InMemoryPubSub()

async with pubsub:
    # Single message
    await pubsub.publish("orders", Message(payload=b"order-1"))

    # Multiple messages
    await pubsub.publish(
        "orders",
        Message(payload=b"order-2"),
        Message(payload=b"order-3"),
    )
```

## Subscriber Protocol

```python
from typing import Protocol, AsyncIterator

class Subscriber(Protocol):
    def subscribe(self, topic: str) -> AsyncIterator[Message]:
        """Subscribe to a topic, yielding messages as they arrive."""
        ...

    async def close(self) -> None:
        """Close the subscriber."""
        ...

    async def __aenter__(self) -> "Subscriber":
        ...

    async def __aexit__(self, *args) -> None:
        ...
```

### Usage

```python
async for msg in pubsub.subscribe("orders"):
    print(f"Received: {msg.payload}")
    await msg.ack()
```

!!! note "Not async"
    `subscribe()` returns an `AsyncIterator`, but is not itself async. The iteration is async.

## InMemoryPubSub

The built-in implementation for testing and development:

```python
from natricine.pubsub import InMemoryPubSub

pubsub = InMemoryPubSub(buffer_size=100)

async with pubsub:
    # Use as both publisher and subscriber
    ...
```

### Fan-out Semantics

InMemoryPubSub broadcasts messages to **all** subscribers:

```python
async with pubsub:
    # Both subscribers receive all messages
    sub1 = pubsub.subscribe("events")
    sub2 = pubsub.subscribe("events")

    await pubsub.publish("events", Message(payload=b"hello"))

    # Both receive it
    msg1 = await anext(sub1)
    msg2 = await anext(sub2)
```

### Backpressure

When the buffer is full, `publish()` blocks until space is available:

```python
pubsub = InMemoryPubSub(buffer_size=10)

# If no subscriber is consuming, this will block after 10 messages
for i in range(100):
    await pubsub.publish("topic", Message(payload=f"msg-{i}".encode()))
```

## Backend Implementations

| Backend | Package | Semantics |
|---------|---------|-----------|
| In-Memory | `natricine` | Fan-out |
| Redis Streams | `natricine-redisstream` | Competing consumers |
| AWS SQS | `natricine-aws` | Competing consumers |
| AWS SNS+SQS | `natricine-aws` | Fan-out per consumer group |
| PostgreSQL | `natricine-sql` | Competing consumers |
| SQLite | `natricine-sql` | Competing consumers |

### Fan-out vs Competing Consumers

**Fan-out**: Every subscriber receives every message. Good for broadcasting events.

**Competing consumers**: Messages are distributed across subscribers in the same group. Good for load balancing work.

```python
# Fan-out (In-Memory, SNS)
# All subscribers get the message
subscriber_a = pubsub.subscribe("events")
subscriber_b = pubsub.subscribe("events")

# Competing consumers (Redis, SQS, SQL)
# Only ONE subscriber gets each message
subscriber_a = RedisStreamSubscriber(redis, group="workers", consumer="a")
subscriber_b = RedisStreamSubscriber(redis, group="workers", consumer="b")
```
