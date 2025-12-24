# AWS SQS/SNS

AWS Simple Queue Service (SQS) and Simple Notification Service (SNS) backend.

## Installation

```bash
pip install natricine-aws
```

## SQS (Queues)

Direct queue-based messaging:

```python
import aioboto3
from natricine_aws import SQSPublisher, SQSSubscriber
from natricine.pubsub import Message

session = aioboto3.Session()

publisher = SQSPublisher(session)
subscriber = SQSSubscriber(session)

# Publish
await publisher.publish("orders", Message(payload=b'{"id": 1}'))

# Subscribe
async for msg in subscriber.subscribe("orders"):
    print(f"Received: {msg.payload}")
    await msg.ack()  # Deletes message from queue
```

## SNS (Pub/Sub)

For fan-out across multiple subscriber groups:

```python
from natricine_aws import SNSPublisher, SNSSubscriber, SNSConfig

# Publisher sends to SNS topic
publisher = SNSPublisher(session)

# Each subscriber group gets its own SQS queue
analytics_sub = SNSSubscriber(
    session,
    config=SNSConfig(consumer_group="analytics")
)
notifications_sub = SNSSubscriber(
    session,
    config=SNSConfig(consumer_group="notifications")
)

# Message goes to both subscriber groups
await publisher.publish("user-events", Message(payload=b"user created"))
```

## Configuration

### SQSConfig

```python
from natricine_aws import SQSConfig

config = SQSConfig(
    wait_time_s=20,           # Long polling wait time (max 20)
    visibility_timeout_s=30,  # Time before message redelivery
    max_messages=10,          # Messages per poll (max 10)
    create_queue_if_missing=True,
)

subscriber = SQSSubscriber(session, config=config)
```

### SNSConfig

```python
from natricine_aws import SNSConfig, SQSConfig

config = SNSConfig(
    consumer_group="my-service",  # Used in SQS queue name
    create_resources=True,        # Auto-create topic, queue, subscription
    sqs_config=SQSConfig(...),    # Underlying SQS settings
)

subscriber = SNSSubscriber(session, config=config)
```

## LocalStack Development

For local development without AWS:

```python
publisher = SQSPublisher(
    session,
    endpoint_url="http://localhost:4566",
    region_name="us-east-1",
)

subscriber = SQSSubscriber(
    session,
    endpoint_url="http://localhost:4566",
    region_name="us-east-1",
)
```

## Characteristics

| Feature | SQS | SNS+SQS |
|---------|-----|---------|
| Delivery | At-least-once | At-least-once |
| Pattern | Competing consumers | Fan-out per group |
| Ordering | FIFO available | Standard only |

## Message Attributes

SQS message attributes are mapped to natricine metadata:

```python
msg = Message(
    payload=b"data",
    metadata={
        "trace_id": "abc-123",
        "content_type": "application/json",
    }
)
await publisher.publish("queue", msg)

# On receive, metadata is preserved
async for msg in subscriber.subscribe("queue"):
    print(msg.metadata["trace_id"])  # "abc-123"
```

## With CQRS

```python
from natricine.cqrs import CommandBus, PydanticMarshaler

command_bus = CommandBus(
    publisher=SQSPublisher(session),
    subscriber=SQSSubscriber(session),
    marshaler=PydanticMarshaler(),
)
```
