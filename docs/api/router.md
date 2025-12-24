# natricine.router

Message routing with handler registration and middleware.

## Installation

```bash
pip install natricine
```

## Router

Routes messages to handlers by topic.

```python
from natricine.router import Router, RouterConfig

router = Router(
    subscriber,
    config=RouterConfig(
        close_timeout=30.0,       # Graceful shutdown timeout
    ),
)

@router.handler("orders")
async def handle_order(msg: Message) -> None:
    process(msg)

# Run router
await router.run()
```

### Constructor

```python
Router(
    subscriber: Subscriber,
    publisher: Publisher | None = None,
    config: RouterConfig | None = None,
)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `subscriber` | `Subscriber` | Source of messages |
| `publisher` | `Publisher \| None` | For handlers that return messages |
| `config` | `RouterConfig \| None` | Router configuration |

### Methods

| Method | Description |
|--------|-------------|
| `handler(topic)` | Decorator to register handler for topic |
| `add_middleware(mw)` | Add middleware to all handlers |
| `await run()` | Start processing messages |
| `await close()` | Stop router gracefully |

## RouterConfig

```python
from natricine.router import RouterConfig

config = RouterConfig(
    close_timeout=30.0,   # Seconds to wait for handlers on shutdown
)
```

## Handler Types

### NoPublishHandlerFunc

Handler that processes messages without returning any:

```python
NoPublishHandlerFunc = Callable[[Message], Awaitable[None]]

@router.handler("orders")
async def handle(msg: Message) -> None:
    process(msg)
```

### HandlerFunc

Handler that may return messages to publish:

```python
HandlerFunc = Callable[[Message], Awaitable[list[Message] | None]]

@router.handler("input")
async def transform(msg: Message) -> list[Message] | None:
    result = process(msg)
    return [Message(payload=result)]
```

## Middleware

### retry

Retry failed handlers with exponential backoff.

```python
from natricine.router import retry

router.add_middleware(retry(
    max_retries=3,              # Maximum retry attempts
    delay=1.0,                  # Initial delay (seconds)
    backoff=2.0,                # Exponential multiplier
    jitter=0.1,                 # Random jitter (0-10%)
    exceptions=(Exception,),    # Exceptions to retry
))
```

### timeout

Cancel handlers exceeding time limit.

```python
from natricine.router import timeout

router.add_middleware(timeout(seconds=30))
```

### dead_letter_queue

Send failed messages to a dead-letter topic.

```python
from natricine.router import dead_letter_queue

router.add_middleware(dead_letter_queue(
    publisher=dlq_publisher,
    topic="orders.dlq",
))
```

### recoverer

Log and acknowledge failed messages (prevents redelivery).

```python
from natricine.router import recoverer

router.add_middleware(recoverer())
```

## PermanentError

Skip retries for unrecoverable errors:

```python
from natricine.router import PermanentError

@router.handler("orders")
async def handle(msg: Message) -> None:
    if is_invalid(msg):
        raise PermanentError("Invalid format")  # Goes to DLQ immediately
    process(msg)
```

## Custom Middleware

```python
from natricine.router import Middleware, HandlerFunc
from natricine.pubsub import Message

def logging_middleware() -> Middleware:
    def middleware(next_handler: HandlerFunc) -> HandlerFunc:
        async def handler(msg: Message) -> list[Message] | None:
            print(f"Processing: {msg.uuid}")
            result = await next_handler(msg)
            print(f"Done: {msg.uuid}")
            return result
        return handler
    return middleware

router.add_middleware(logging_middleware())
```

## Middleware Type

```python
Middleware = Callable[[HandlerFunc], HandlerFunc]
```

Middleware wraps handlers. First middleware added is outermost:

```python
router.add_middleware(retry(...))     # Outermost
router.add_middleware(timeout(...))   # Middle
router.add_middleware(logging(...))   # Innermost

# Execution: retry -> timeout -> logging -> handler
```
