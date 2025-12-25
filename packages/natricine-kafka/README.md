# natricine-kafka

Apache Kafka pub/sub implementation using aiokafka.

## Installation

```bash
pip install natricine-kafka
```

## Usage

```python
import asyncio
from natricine.pubsub import Message
from natricine_kafka import KafkaPublisher, KafkaSubscriber, ProducerConfig, ConsumerConfig

async def main():
    publisher = KafkaPublisher(ProducerConfig(bootstrap_servers="localhost:9092"))
    subscriber = KafkaSubscriber(ConsumerConfig(
        bootstrap_servers="localhost:9092",
        group_id="my-service",
    ))

    # Publish
    async with publisher:
        await publisher.publish("orders", Message(payload=b'{"id": 1}'))

    # Subscribe (consumer group ensures each message processed once)
    async with subscriber:
        async for msg in subscriber.subscribe("orders"):
            print(f"Received: {msg.payload}")
            await msg.ack()  # Commits offset to Kafka
            break

asyncio.run(main())
```

## Consumer Groups

Kafka consumer groups provide:
- **Competing consumers**: Messages distributed across workers in same group
- **At-least-once delivery**: Nack seeks back to message offset for redelivery
- **Offset tracking**: Kafka tracks committed offsets per consumer group

```python
# Multiple workers in same group share the load
subscriber1 = KafkaSubscriber(ConsumerConfig(group_id="order-processors"))
subscriber2 = KafkaSubscriber(ConsumerConfig(group_id="order-processors"))

# Different groups each get all messages (fan-out)
analytics = KafkaSubscriber(ConsumerConfig(group_id="analytics"))
notifications = KafkaSubscriber(ConsumerConfig(group_id="notifications"))
```

## Configuration

### Producer

```python
ProducerConfig(
    bootstrap_servers="localhost:9092",  # Kafka broker addresses
    client_id="my-app",                  # Client identifier
    acks="all",                          # Wait for all replicas (default)
    retry_backoff_ms=100,                # Retry backoff (default: 100)
    uuid_header="_natricine_message_uuid",  # Header for message UUID
)
```

### Consumer

```python
ConsumerConfig(
    bootstrap_servers="localhost:9092",
    client_id="my-app",
    group_id="my-service",               # Consumer group (required for competing consumers)
    auto_offset_reset="earliest",        # Where to start: earliest, latest (default: earliest)
    enable_auto_commit=False,            # Manual commit on ack (default: False)
    max_poll_records=10,                 # Max messages per poll (default: 10)
    uuid_header="_natricine_message_uuid",
)
```

## With CQRS

```python
from natricine.cqrs import CommandBus, PydanticMarshaler

marshaler = PydanticMarshaler()
command_bus = CommandBus(
    publisher=KafkaPublisher(ProducerConfig(bootstrap_servers="localhost:9092")),
    subscriber=KafkaSubscriber(ConsumerConfig(
        bootstrap_servers="localhost:9092",
        group_id="commands",
    )),
    marshaler=marshaler,
)
```

## Watermill Interoperability

To interoperate with Go services using watermill-kafka, configure the UUID header:

```python
# Match watermill's header convention
config = ProducerConfig(
    bootstrap_servers="localhost:9092",
    uuid_header="_watermill_message_uuid",
)
```
