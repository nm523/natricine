# natricine-http

HTTP pub/sub backend for natricine. Send and receive webhooks.

## Installation

```bash
pip install natricine-http
```

## HTTPPublisher

Send messages as HTTP POST requests:

```python
from natricine.backends.http import HTTPPublisher, HTTPPublisherConfig
from natricine.pubsub import Message

config = HTTPPublisherConfig(base_url="http://api.example.com")

async with HTTPPublisher(config) as publisher:
    await publisher.publish("orders", Message(payload=b'{"id": 1}'))
    # POSTs to http://api.example.com/orders
```

### Configuration

```python
HTTPPublisherConfig(
    base_url="http://api.example.com",   # Required
    topic_path="/{topic}",               # URL pattern (default)
    timeout_s=30.0,                      # Request timeout
    headers={"Authorization": "Bearer token"},  # Default headers
)
```

## HTTPSubscriber

Receive webhooks via a Starlette ASGI app:

```python
import asyncio
from fastapi import FastAPI
from natricine.backends.http import HTTPSubscriber

app = FastAPI()
subscriber = HTTPSubscriber()

# Mount at /webhooks - receives POSTs at /webhooks/{topic}
app.mount("/webhooks", subscriber.app)

@app.on_event("startup")
async def start_worker():
    asyncio.create_task(process_orders())

async def process_orders():
    async for msg in subscriber.subscribe("orders"):
        print(f"Received: {msg.payload}")
        await msg.ack()  # Returns 200 to sender

@app.on_event("shutdown")
async def shutdown():
    await subscriber.close()
```

### Ack/Nack Behavior

- `await msg.ack()` - Returns HTTP 200 to webhook sender
- `await msg.nack()` - Returns HTTP 500 to webhook sender

## With Router

```python
from natricine.router import Router

router = Router(subscriber)

@router.handler("orders")
async def handle_order(msg: Message) -> None:
    process(msg)

# Router auto-acks on success, nacks on exception
await router.run()
```

## Message Format

**Headers:**
- `X-Natricine-UUID` - Message UUID
- `X-Natricine-Meta-{key}` - Metadata entries
- `Content-Type` - Payload type (default: application/octet-stream)

**Body:** Raw message payload

## Characteristics

| Feature | Behavior |
|---------|----------|
| Delivery | At-most-once |
| Pattern | Request-response |
| Persistence | None |
