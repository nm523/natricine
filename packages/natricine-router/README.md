# natricine-router

Message routing with middleware support.

Part of the `natricine` package - install via `pip install natricine`.

## Usage

```python
import asyncio
from natricine.pubsub import InMemoryPubSub, Message
from natricine.router import Router, retry, timeout

async def main():
    async with InMemoryPubSub() as pubsub:
        router = Router()

        # Add middleware (applies to all handlers)
        router.add_middleware(retry(max_retries=3))
        router.add_middleware(timeout(seconds=30))

        # Handler that transforms messages
        async def process_order(msg: Message) -> list[Message] | None:
            order = json.loads(msg.payload)
            return [Message(payload=json.dumps({"confirmed": order["id"]}).encode())]

        router.add_handler(
            name="order-processor",
            subscribe_topic="orders.new",
            subscriber=pubsub,
            publish_topic="orders.confirmed",
            publisher=pubsub,
            handler_func=process_order,
        )

        # Handler that consumes only (no output)
        async def log_order(msg: Message) -> None:
            print(f"Order received: {msg.payload}")

        router.add_no_publisher_handler(
            name="order-logger",
            subscribe_topic="orders.new",
            subscriber=pubsub,
            handler_func=log_order,
        )

        await router.run()

asyncio.run(main())
```

## Middleware

Middleware wraps handlers: `Callable[[HandlerFunc], HandlerFunc]`

### Built-in Middleware

```python
from natricine.router import retry, timeout, recoverer, dead_letter_queue, PermanentError

# Retry with exponential backoff
retry(
    max_retries=3,
    delay=1.0,           # Initial delay
    backoff=2.0,         # Multiplier per retry
    jitter=0.1,          # ±10% randomization
    retry_on=(ValueError,),  # Only retry these (default: all)
    on_retry=lambda attempt, exc, msg: print(f"Retry {attempt}"),
)

# Timeout
timeout(seconds=30)

# Log exceptions without crashing
recoverer(logger=my_logger)

# Send failed messages to dead letter queue
dead_letter_queue(publisher=dlq_publisher, topic="failed-messages")

# Skip retries for unrecoverable errors
raise PermanentError(ValueError("Invalid input"))
```

### Custom Middleware

```python
def logging_middleware(handler: HandlerFunc) -> HandlerFunc:
    async def wrapper(msg: Message) -> list[Message] | None:
        print(f"Processing {msg.uuid}")
        result = await handler(msg)
        print(f"Done {msg.uuid}")
        return result
    return wrapper

router.add_middleware(logging_middleware)
```
