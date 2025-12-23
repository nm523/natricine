# Router & Handlers

The Router provides a higher-level abstraction for handling messages with middleware support.

## Basic Usage

```python
from natricine.pubsub import InMemoryPubSub, Message
from natricine.router import Router

pubsub = InMemoryPubSub()
router = Router(pubsub)

@router.handler("orders")
async def handle_order(msg: Message) -> None:
    order = json.loads(msg.payload)
    print(f"Processing order: {order['id']}")

async with pubsub:
    await router.run()  # Blocks, processing messages
```

## Handler Registration

### Decorator Style

```python
@router.handler("topic-name")
async def my_handler(msg: Message) -> None:
    ...
```

### Programmatic

```python
async def my_handler(msg: Message) -> None:
    ...

router.add_handler("topic-name", my_handler)
```

## Multiple Handlers

Register multiple handlers for different topics:

```python
@router.handler("orders")
async def handle_orders(msg: Message) -> None:
    ...

@router.handler("payments")
async def handle_payments(msg: Message) -> None:
    ...

@router.handler("notifications")
async def handle_notifications(msg: Message) -> None:
    ...
```

## Handler Lifecycle

```python
async with pubsub:
    # Start processing messages
    task = asyncio.create_task(router.run())

    # ... your application logic ...

    # Graceful shutdown
    await router.close()
    await task
```

## Acknowledgment

By default, the router **does not auto-ack**. You must ack/nack in your handler:

```python
@router.handler("orders")
async def handle_order(msg: Message) -> None:
    try:
        process(msg)
        await msg.ack()  # Explicit ack
    except Exception:
        await msg.nack()  # Explicit nack for redelivery
```

## Error Handling

Unhandled exceptions in handlers will:

1. Not ack the message (leaves it pending)
2. Propagate up (unless caught by middleware)

Use middleware for automatic retry/error handling:

```python
from natricine.router import retry

router.add_middleware(retry(max_retries=3))

@router.handler("orders")
async def handle_order(msg: Message) -> None:
    # Will be retried up to 3 times on failure
    process(msg)
    await msg.ack()
```

## Concurrent Processing

The router processes messages from each topic concurrently:

```python
# Messages from different topics processed in parallel
@router.handler("orders")
async def orders(msg): ...

@router.handler("payments")
async def payments(msg): ...

# Both handlers run concurrently when router.run() is called
```

Within a single topic, messages are processed sequentially by default. For parallel processing within a topic, use a task group in your handler.
