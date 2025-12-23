# In-Memory

The built-in `InMemoryPubSub` is perfect for testing and development.

## Installation

Included in the core package:

```bash
pip install natricine
```

## Usage

```python
from natricine.pubsub import InMemoryPubSub, Message

async with InMemoryPubSub() as pubsub:
    # Subscribe
    async def consumer():
        async for msg in pubsub.subscribe("orders"):
            print(f"Received: {msg.payload}")
            await msg.ack()

    # Publish
    await pubsub.publish("orders", Message(payload=b"order-123"))
```

## Configuration

```python
pubsub = InMemoryPubSub(
    buffer_size=100,  # Messages buffered per subscriber (default: 100)
)
```

## Characteristics

| Feature | Behavior |
|---------|----------|
| Delivery | At-most-once |
| Pattern | Fan-out (all subscribers get all messages) |
| Persistence | None (messages lost on close) |
| Backpressure | Blocks publisher when buffer full |

## Fan-out Semantics

All subscribers receive all messages:

```python
async with pubsub:
    # Both receive the message
    sub1_task = asyncio.create_task(consume(pubsub.subscribe("events")))
    sub2_task = asyncio.create_task(consume(pubsub.subscribe("events")))

    await pubsub.publish("events", Message(payload=b"hello"))
    # sub1 gets "hello"
    # sub2 gets "hello"
```

## Testing

InMemoryPubSub is ideal for unit tests:

```python
import pytest
from natricine.pubsub import InMemoryPubSub

@pytest.fixture
async def pubsub():
    async with InMemoryPubSub() as ps:
        yield ps

async def test_order_handler(pubsub):
    received = []

    async def handler():
        async for msg in pubsub.subscribe("orders"):
            received.append(msg)
            await msg.ack()
            break

    async with asyncio.TaskGroup() as tg:
        tg.create_task(handler())
        await asyncio.sleep(0.01)
        await pubsub.publish("orders", Message(payload=b"test"))
        await asyncio.sleep(0.01)

    assert len(received) == 1
    assert received[0].payload == b"test"
```

## Limitations

- **No persistence**: Messages are lost when the process exits
- **Single process**: Cannot share messages across processes
- **No competing consumers**: All subscribers get all messages

For production, use [Redis](redis.md), [AWS](aws.md), or [SQL](sql.md) backends.
