# Quick Start

This guide walks you through building a simple event-driven application with natricine.

## Basic Pub/Sub

The simplest way to use natricine is with the in-memory pub/sub:

```python
import asyncio
from natricine.pubsub import InMemoryPubSub, Message

async def main():
    pubsub = InMemoryPubSub()

    async with pubsub:
        # Start a subscriber
        async def subscriber():
            async for msg in pubsub.subscribe("orders"):
                print(f"Received: {msg.payload.decode()}")
                await msg.ack()

        # Run subscriber in background
        async with asyncio.TaskGroup() as tg:
            tg.create_task(subscriber())

            # Give subscriber time to start
            await asyncio.sleep(0.01)

            # Publish a message
            await pubsub.publish("orders", Message(payload=b"order-123"))

            await asyncio.sleep(0.1)
            await pubsub.close()

asyncio.run(main())
```

## Using the Router

For more complex message handling, use the Router with handlers:

```python
import asyncio
from natricine.pubsub import InMemoryPubSub, Message
from natricine.router import Router

async def main():
    pubsub = InMemoryPubSub()
    router = Router(pubsub)

    @router.handler("orders")
    async def handle_order(msg: Message) -> None:
        print(f"Processing order: {msg.payload.decode()}")

    async with pubsub:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(router.run())

            await asyncio.sleep(0.01)
            await pubsub.publish("orders", Message(payload=b"order-456"))

            await asyncio.sleep(0.1)
            await router.close()

asyncio.run(main())
```

## CQRS Pattern

For domain-driven design, use CommandBus and EventBus:

```python
import asyncio
from natricine.pubsub import InMemoryPubSub
from natricine.cqrs import CommandBus, EventBus, PydanticMarshaler
from pydantic import BaseModel

# Define your domain models
class CreateOrder(BaseModel):
    order_id: str
    customer: str

class OrderCreated(BaseModel):
    order_id: str
    customer: str

async def main():
    pubsub = InMemoryPubSub()
    marshaler = PydanticMarshaler()

    command_bus = CommandBus(pubsub, pubsub, marshaler)
    event_bus = EventBus(pubsub, pubsub, marshaler)

    # Command handler - processes one command
    @command_bus.handler
    async def handle_create_order(cmd: CreateOrder) -> None:
        print(f"Creating order {cmd.order_id} for {cmd.customer}")
        # Publish event after processing
        await event_bus.publish(OrderCreated(
            order_id=cmd.order_id,
            customer=cmd.customer
        ))

    # Event handlers - react to events
    @event_bus.handler
    async def send_confirmation(event: OrderCreated) -> None:
        print(f"Sending confirmation for order {event.order_id}")

    @event_bus.handler
    async def update_inventory(event: OrderCreated) -> None:
        print(f"Updating inventory for order {event.order_id}")

    async with pubsub:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(command_bus.run())
            tg.create_task(event_bus.run())

            # Send a command
            await command_bus.send(CreateOrder(
                order_id="ORD-001",
                customer="Alice"
            ))

            await asyncio.sleep(0.1)
            await command_bus.close()
            await event_bus.close()

asyncio.run(main())
```

Output:
```
Creating order ORD-001 for Alice
Sending confirmation for order ORD-001
Updating inventory for order ORD-001
```

## Adding Middleware

Enhance reliability with middleware:

```python
from natricine.router import Router, retry, timeout

router = Router(pubsub)

# Retry failed handlers up to 3 times
router.add_middleware(retry(max_retries=3, delay=1.0))

# Timeout after 30 seconds
router.add_middleware(timeout(seconds=30))

@router.handler("orders")
async def handle_order(msg: Message) -> None:
    # This handler will be retried on failure
    # and cancelled if it takes > 30 seconds
    ...
```

## Next Steps

- Learn about [Messages](../concepts/messages.md) and the pub/sub protocol
- Explore [Backends](../backends/index.md) for production deployments
- Add [OpenTelemetry](../observability/otel.md) for observability
