# Middleware

Middleware wraps handlers to add cross-cutting concerns like retry, timeout, and logging.

## Using Middleware

```python
from natricine.router import Router, retry, timeout

router = Router(subscriber)

# Add middleware (order matters - first added wraps outermost)
router.add_middleware(retry(max_retries=3))
router.add_middleware(timeout(seconds=30))

@router.handler("orders")
async def handle_order(msg: Message) -> None:
    ...
```

## Built-in Middleware

### retry

Retry failed handlers with configurable backoff:

```python
from natricine.router import retry, PermanentError

router.add_middleware(retry(
    max_retries=3,           # Maximum retry attempts
    delay=1.0,               # Initial delay in seconds
    backoff=2.0,             # Multiplier for exponential backoff
    jitter=0.1,              # Random jitter (0-10% of delay)
    exceptions=(Exception,), # Which exceptions to retry
    on_retry=log_retry,      # Callback on each retry
))

@router.handler("orders")
async def handle_order(msg: Message) -> None:
    if is_invalid(msg):
        # Don't retry - move to DLQ immediately
        raise PermanentError("Invalid message format")

    # This will be retried on failure
    process(msg)
```

### timeout

Cancel handlers that take too long:

```python
from natricine.router import timeout

router.add_middleware(timeout(seconds=30))

@router.handler("orders")
async def handle_order(msg: Message) -> None:
    # Cancelled if takes > 30 seconds
    await slow_operation()
```

### dead_letter_queue

Send failed messages to a dead-letter queue:

```python
from natricine.router import dead_letter_queue

router.add_middleware(dead_letter_queue(
    publisher=dlq_publisher,
    topic="orders.dlq",
))

@router.handler("orders")
async def handle_order(msg: Message) -> None:
    # If this raises, message goes to orders.dlq
    process(msg)
```

## Custom Middleware

Middleware is a function that wraps a handler:

```python
from natricine.router import Handler, Middleware
from natricine.pubsub import Message

def logging_middleware() -> Middleware:
    async def middleware(msg: Message, handler: Handler) -> None:
        print(f"Processing: {msg.uuid}")
        try:
            await handler(msg)
            print(f"Success: {msg.uuid}")
        except Exception as e:
            print(f"Failed: {msg.uuid} - {e}")
            raise

    return middleware

router.add_middleware(logging_middleware())
```

### Middleware Signature

```python
Middleware = Callable[[Message, Handler], Awaitable[None]]
Handler = Callable[[Message], Awaitable[None]]
```

## Middleware Order

Middleware is applied in reverse order of addition (first added = outermost):

```python
router.add_middleware(retry(...))    # Outermost
router.add_middleware(timeout(...))  # Middle
router.add_middleware(logging(...))  # Innermost

# Execution order:
# retry → timeout → logging → handler → logging → timeout → retry
```

## Combining Middleware

```python
from natricine.router import retry, timeout, dead_letter_queue

# Robust production setup
router.add_middleware(dead_letter_queue(dlq_publisher, "errors.dlq"))
router.add_middleware(retry(max_retries=3, delay=1.0, backoff=2.0))
router.add_middleware(timeout(seconds=60))

@router.handler("orders")
async def handle_order(msg: Message) -> None:
    # 1. Timeout after 60 seconds
    # 2. Retry up to 3 times with exponential backoff
    # 3. After all retries exhausted, send to DLQ
    await process_order(msg)
```

## OpenTelemetry Middleware

For distributed tracing, see [OpenTelemetry](../observability/otel.md):

```python
from natricine.otel import TracingMiddleware

router.add_middleware(TracingMiddleware())
```
