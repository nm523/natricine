# natricine-pubsub

Core pub/sub abstractions and in-memory implementation.

## Installation

```bash
pip install natricine-pubsub
```

## Message

A message with payload and metadata.

```python
from natricine.pubsub import Message

msg = Message(
    payload=b"data",                        # Required: binary payload
    metadata={"key": "value"},              # Optional: string key-value pairs
    uuid=uuid.uuid4(),                      # Optional: auto-generated if not set
)

# Acknowledge (mark as processed)
await msg.ack()

# Negative acknowledge (trigger redelivery)
await msg.nack()
```

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `payload` | `bytes` | Message content |
| `metadata` | `dict[str, str]` | Key-value metadata |
| `uuid` | `UUID` | Unique message identifier |

### Methods

| Method | Description |
|--------|-------------|
| `await ack()` | Acknowledge successful processing |
| `await nack()` | Signal processing failure for redelivery |

## Publisher

Protocol for publishing messages.

```python
from natricine.pubsub import Publisher

class Publisher(Protocol):
    async def publish(self, topic: str, *messages: Message) -> None: ...
    async def close(self) -> None: ...
```

### Usage

```python
publisher: Publisher = ...

# Single message
await publisher.publish("orders", Message(payload=b"data"))

# Multiple messages
await publisher.publish("orders", msg1, msg2, msg3)

# Cleanup
await publisher.close()
```

## Subscriber

Protocol for subscribing to topics.

```python
from natricine.pubsub import Subscriber

class Subscriber(Protocol):
    def subscribe(self, topic: str) -> AsyncIterator[Message]: ...
    async def close(self) -> None: ...
```

### Usage

```python
subscriber: Subscriber = ...

async for msg in subscriber.subscribe("orders"):
    try:
        process(msg)
        await msg.ack()
    except Exception:
        await msg.nack()
```

## InMemoryPubSub

In-memory pub/sub for testing and development.

```python
from natricine.pubsub import InMemoryPubSub

async with InMemoryPubSub() as pubsub:
    # Subscribe
    async for msg in pubsub.subscribe("topic"):
        await msg.ack()

    # Publish
    await pubsub.publish("topic", Message(payload=b"data"))
```

### Constructor

```python
InMemoryPubSub(buffer_size: int = 100)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `buffer_size` | `int` | `100` | Messages buffered per subscriber |

### Behavior

- **Fan-out**: All subscribers receive all messages
- **At-most-once**: Messages not persisted
- **Backpressure**: Blocks publisher when buffer full
