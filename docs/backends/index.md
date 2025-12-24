# Backends

Natricine supports multiple message backends through its Protocol-based architecture.

## Available Backends

| Backend | Package | Description |
|---------|---------|-------------|
| [In-Memory](memory.md) | `natricine` | Built-in, no external dependencies |
| [Redis Streams](redis.md) | `natricine-redisstream` | Redis streams with consumer groups |
| [AWS SQS/SNS](aws.md) | `natricine-aws` | Managed AWS messaging services |
| [SQL](sql.md) | `natricine-sql` | PostgreSQL and SQLite with polling |

## Backend Characteristics

### In-Memory

- Zero setup, included in core package
- No persistence - messages lost on exit
- Fan-out to all subscribers

### Redis Streams

- Persistent message storage
- Consumer groups for competing consumers

### AWS SQS/SNS

- Fully managed by AWS
- SQS for queues, SNS for pub/sub
- SNS+SQS combination for fan-out with durability

### SQL (Postgres/SQLite)

- Uses existing database infrastructure
- Polling-based subscriber
- `FOR UPDATE SKIP LOCKED` for competing consumers (Postgres)

## Semantics Comparison

| Backend | Delivery | Pattern |
|---------|----------|---------|
| In-Memory | At-most-once | Fan-out |
| Redis Streams | At-least-once | Competing consumers |
| AWS SQS | At-least-once | Competing consumers |
| AWS SNS+SQS | At-least-once | Fan-out per consumer group |
| SQL | At-least-once | Competing consumers |

## Swapping Backends

Because all backends implement the same Protocol, swapping is straightforward:

```python
# Development
from natricine.pubsub import InMemoryPubSub
pubsub = InMemoryPubSub()

# Production (Redis)
from natricine_redis import RedisStreamPublisher, RedisStreamSubscriber
publisher = RedisStreamPublisher(redis)
subscriber = RedisStreamSubscriber(redis, "myapp", "worker-1")

# Production (SQS)
from natricine_aws import SQSPublisher, SQSSubscriber
publisher = SQSPublisher(session)
subscriber = SQSSubscriber(session)
```

Your handler code stays the same regardless of backend.
