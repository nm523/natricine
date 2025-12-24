# SQL (PostgreSQL/SQLite)

## Installation

```bash
# PostgreSQL
pip install natricine-sql[postgres]

# SQLite (for testing)
pip install natricine-sql[sqlite]
```

## PostgreSQL Usage

```python
import asyncpg
from natricine_sql import SQLPublisher, SQLSubscriber, SQLConfig, PostgresDialect

pool = await asyncpg.create_pool("postgres://user:pass@localhost/db")

dialect = PostgresDialect()
config = SQLConfig(consumer_group="my-service")

publisher = SQLPublisher(pool, dialect, config)
subscriber = SQLSubscriber(pool, dialect, config)

# Publish
from natricine.pubsub import Message
await publisher.publish("orders", Message(payload=b'{"id": 1}'))

# Subscribe
async for msg in subscriber.subscribe("orders"):
    print(f"Received: {msg.payload}")
    await msg.ack()
```

## SQLite Usage

```python
import aiosqlite
from natricine_sql import SQLPublisher, SQLSubscriber, SQLConfig, SQLiteDialect

conn = await aiosqlite.connect(":memory:")

dialect = SQLiteDialect()
config = SQLConfig(consumer_group="test")

publisher = SQLPublisher(conn, dialect, config)
subscriber = SQLSubscriber(conn, dialect, config)
```

## Configuration

```python
from natricine_sql import SQLConfig

config = SQLConfig(
    consumer_group="my-service",   # Consumer group name
    poll_interval=1.0,             # Seconds between polls
    ack_deadline=30.0,             # Visibility timeout
    batch_size=10,                 # Messages per poll
    table_prefix="natricine_",     # Table name prefix
    auto_create_tables=True,       # Create tables if missing
)
```

## Table Schema

Each topic creates a table:

```sql
CREATE TABLE natricine_orders (
    id BIGSERIAL PRIMARY KEY,
    uuid UUID NOT NULL,
    payload BYTEA NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    consumer_group VARCHAR(255) NOT NULL,
    claimed_at TIMESTAMPTZ,
    acked_at TIMESTAMPTZ,
    delivery_count INTEGER NOT NULL DEFAULT 0,
    next_delivery_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

## Competing Consumers

PostgreSQL uses `FOR UPDATE SKIP LOCKED` for competing consumers:

```python
# Multiple workers share the load
worker1 = SQLSubscriber(pool, dialect, SQLConfig(consumer_group="processors"))
worker2 = SQLSubscriber(pool, dialect, SQLConfig(consumer_group="processors"))
# Message goes to worker1 OR worker2, not both
```

## Visibility Timeout

Messages have an `ack_deadline` (visibility timeout):

- When a message is claimed, `next_delivery_at` is set to `NOW() + ack_deadline`
- If not acknowledged within the deadline, the message becomes available again
- `delivery_count` is incremented on each delivery

```python
async for msg in subscriber.subscribe("orders"):
    try:
        await process(msg)
        await msg.ack()   # Message marked as processed
    except Exception:
        await msg.nack()  # Immediate redelivery
        # Or let timeout expire for delayed redelivery
```

## Characteristics

| Feature | Behavior |
|---------|----------|
| Delivery | At-least-once |
| Pattern | Competing consumers |
| Persistence | Yes (database) |
| Ordering | Approximate FIFO |

## Dialects

### PostgresDialect

- Uses `$1, $2, ...` placeholders
- `FOR UPDATE SKIP LOCKED` for competing consumers
- `BIGSERIAL` for auto-increment IDs
- `BYTEA` for binary payloads
- `JSONB` for metadata

### SQLiteDialect

- Uses `?` placeholders
- No `SKIP LOCKED` (serialized access)
- `INTEGER PRIMARY KEY AUTOINCREMENT` for IDs
- `BLOB` for binary payloads
- `TEXT` for JSON metadata

## With CQRS

```python
from natricine.cqrs import CommandBus, PydanticMarshaler

command_bus = CommandBus(
    publisher=SQLPublisher(pool, dialect, config),
    subscriber=SQLSubscriber(pool, dialect, config),
    marshaler=PydanticMarshaler(),
)
```
