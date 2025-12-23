# natricine-pubsub

Core pub/sub abstractions for natricine.

Part of the `natricine` package - install via `pip install natricine`.

## Usage

```python
import asyncio
from natricine.pubsub import InMemoryPubSub, Message

async def main():
    async with InMemoryPubSub() as pubsub:
        # Subscribe
        async def consume():
            async for msg in pubsub.subscribe("orders"):
                print(f"Received: {msg.payload}")
                await msg.ack()

        task = asyncio.create_task(consume())

        # Publish
        await pubsub.publish("orders", Message(payload=b'{"id": 1}'))

        await asyncio.sleep(0.1)
        task.cancel()

asyncio.run(main())
```

## API

### Message

```python
Message(
    payload: bytes,                    # Required
    metadata: dict[str, str] = {},     # Optional key-value pairs
    uuid: UUID = auto-generated,       # Message ID
)

await msg.ack()   # Acknowledge successful processing
await msg.nack()  # Negative acknowledge (redelivery)
```

### Publisher Protocol

```python
class Publisher(Protocol):
    async def publish(self, topic: str, *messages: Message) -> None: ...
    async def close(self) -> None: ...
```

### Subscriber Protocol

```python
class Subscriber(Protocol):
    def subscribe(self, topic: str) -> AsyncIterator[Message]: ...
    async def close(self) -> None: ...
```

### InMemoryPubSub

Built-in implementation for testing and development. Supports fan-out (multiple subscribers receive all messages).

## Implementations

- `natricine-redisstream` - Redis Streams
- `natricine-aws` - AWS SQS/SNS
