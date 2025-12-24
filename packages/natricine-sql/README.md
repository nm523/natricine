# natricine-sql

SQL-based pub/sub implementation supporting PostgreSQL and SQLite.

## Installation

```bash
# For PostgreSQL
pip install natricine-sql[postgres]

# For SQLite (dev/testing)
pip install natricine-sql[sqlite]
```

## Usage

### SQLite (Development/Testing)

```python
import asyncio
import aiosqlite
from natricine.pubsub import Message
from natricine.backends.sql import SQLConfig, SQLiteDialect, SQLPublisher, SQLSubscriber

async def main():
    conn = await aiosqlite.connect("messages.db")
    dialect = SQLiteDialect()
    config = SQLConfig(consumer_group="my-service")

    publisher = SQLPublisher(conn, dialect, config)
    subscriber = SQLSubscriber(conn, dialect, config)

    # Publish
    await publisher.publish("orders", Message(payload=b'{"id": 1}'))

    # Subscribe (competing consumers)
    async for msg in subscriber.subscribe("orders"):
        print(f"Received: {msg.payload}")
        await msg.ack()
        break

    await conn.close()

asyncio.run(main())
```

### PostgreSQL (Production)

```python
import asyncio
import asyncpg
from natricine.pubsub import Message
from natricine.backends.sql import SQLConfig, PostgresDialect, SQLPublisher, SQLSubscriber

async def main():
    pool = await asyncpg.create_pool("postgresql://localhost/mydb")
    dialect = PostgresDialect()
    config = SQLConfig(consumer_group="my-service")

    publisher = SQLPublisher(pool, dialect, config)
    subscriber = SQLSubscriber(pool, dialect, config)

    async with publisher, subscriber:
        await publisher.publish("orders", Message(payload=b'{"id": 1}'))

        async for msg in subscriber.subscribe("orders"):
            print(f"Received: {msg.payload}")
            await msg.ack()
            break

    await pool.close()

asyncio.run(main())
```

## Competing Consumers

SQL pub/sub uses a competing consumers pattern (like SQS):
- **Per-message acknowledgment**: Each message tracked individually
- **Visibility timeout**: Unacked messages redelivered after `ack_deadline`
- **FOR UPDATE SKIP LOCKED**: PostgreSQL ensures no duplicate processing

```python
# Multiple workers share the load
config = SQLConfig(consumer_group="order-processors")

# Worker 1
subscriber1 = SQLSubscriber(pool, dialect, config)

# Worker 2 (same consumer_group = competing)
subscriber2 = SQLSubscriber(pool, dialect, config)
```

## Configuration

```python
SQLConfig(
    consumer_group="default",     # Consumer group name
    poll_interval=1.0,            # Seconds between polls when idle
    ack_deadline=30.0,            # Visibility timeout in seconds
    batch_size=10,                # Max messages per poll
    table_prefix="natricine_",    # Table name prefix
    auto_create_tables=True,      # Auto-create tables
)
```

## Table Schema

Tables are auto-created with this structure:

```sql
CREATE TABLE natricine_{topic} (
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

## With CQRS

```python
from natricine.cqrs import CommandBus, PydanticMarshaler

marshaler = PydanticMarshaler()
command_bus = CommandBus(
    publisher=SQLPublisher(pool, dialect, config),
    subscriber=SQLSubscriber(pool, dialect, config),
    marshaler=marshaler,
)
```

## SQLite Limitations

SQLite is suitable for development and testing but has limitations:
- No `FOR UPDATE SKIP LOCKED` (uses workaround)
- Single-writer concurrency
- Not recommended for production competing consumers
