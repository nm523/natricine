# Messages

The `Message` class is the fundamental unit of data in natricine.

## Structure

```python
from natricine.pubsub import Message

msg = Message(
    payload=b'{"order_id": "123"}',  # Required: bytes
    metadata={"trace_id": "abc"},     # Optional: dict[str, str]
    uuid=uuid4(),                     # Auto-generated if not provided
)
```

### Payload

The payload is always **bytes**. This is intentional:

- No implicit serialization magic
- You control the format (JSON, protobuf, msgpack, etc.)

```python
import json

# Serialize your data explicitly
data = {"order_id": "123", "amount": 99.99}
msg = Message(payload=json.dumps(data).encode())

# Deserialize on the receiving end
received_data = json.loads(msg.payload.decode())
```

### Metadata

Key-value string pairs for enrichment without touching the payload:

```python
msg = Message(
    payload=b"...",
    metadata={
        "trace_id": "abc-123",
        "correlation_id": "order-flow-1",
        "content_type": "application/json",
    }
)
```

Metadata is preserved through publish/subscribe and is useful for:

- Distributed tracing (trace IDs, span IDs)
- Correlation IDs for request tracking
- Content type hints
- Custom routing information

### UUID

Each message has a unique identifier:

```python
msg = Message(payload=b"...")
print(msg.uuid)  # UUID('a1b2c3d4-...')
```

The UUID is auto-generated but can be set explicitly for idempotency:

```python
from uuid import UUID

msg = Message(
    payload=b"...",
    uuid=UUID("12345678-1234-5678-1234-567812345678")
)
```

## Acknowledgment

Messages must be acknowledged after processing:

```python
async for msg in subscriber.subscribe("orders"):
    try:
        await process_order(msg.payload)
        await msg.ack()  # Success - message processed
    except Exception:
        await msg.nack()  # Failure - message should be redelivered
```

### ack()

Signals successful processing. The message is removed from the queue.

```python
await msg.ack()
```

### nack()

Signals failed processing. The message will be redelivered (behavior depends on backend).

```python
await msg.nack()
```

### Rules

- **Async**: Both `ack()` and `nack()` are async (may involve I/O)
- **Mutually exclusive**: Can't both ack and nack the same message
- **Once only**: Double-acking or double-nacking raises `ValueError`

```python
await msg.ack()
await msg.ack()  # ValueError: Message already acked

await msg.ack()
await msg.nack()  # ValueError: Cannot nack a message that has been acked
```

### State Properties

Check acknowledgment state:

```python
msg.acked   # True if ack() was called
msg.nacked  # True if nack() was called
```

## Copying Messages

For fan-out scenarios, use `copy()` to create independent copies:

```python
original = Message(payload=b"data")
copy = original.copy()

# Same payload and UUID
assert copy.payload == original.payload
assert copy.uuid == original.uuid

# Independent ack state
await original.ack()
assert original.acked
assert not copy.acked  # Copy is independent
```
