# natricine-aws

AWS SQS and SNS pub/sub implementation.

## Installation

```bash
pip install natricine-aws
```

## SQS (Simple Queue)

Direct queue messaging with competing consumers.

```python
import asyncio
import aioboto3
from natricine.pubsub import Message
from natricine_aws import SQSPublisher, SQSSubscriber, SQSConfig

async def main():
    session = aioboto3.Session()

    async with SQSPublisher(session) as publisher:
        async with SQSSubscriber(session, SQSConfig()) as subscriber:
            # Publish
            await publisher.publish("my-queue", Message(payload=b'{"order": 1}'))

            # Subscribe
            async for msg in subscriber.subscribe("my-queue"):
                print(f"Received: {msg.payload}")
                await msg.ack()  # Deletes from queue
                break

asyncio.run(main())
```

### SQS IAM Permissions

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "sqs:SendMessage",
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:ChangeMessageVisibility",
        "sqs:GetQueueUrl",
        "sqs:GetQueueAttributes",
        "sqs:CreateQueue"
      ],
      "Resource": "arn:aws:sqs:*:*:my-queue"
    }
  ]
}
```

Remove `sqs:CreateQueue` if `create_queue_if_missing=False`.

## SNS+SQS (Fan-out)

Pub/sub with fan-out to multiple consumer groups.

```python
from natricine_aws import SNSPublisher, SNSSubscriber, SNSConfig

async def main():
    session = aioboto3.Session()

    async with SNSPublisher(session) as publisher:
        # Two consumer groups - each gets all messages
        config_a = SNSConfig(consumer_group="email-service")
        config_b = SNSConfig(consumer_group="analytics")

        async with SNSSubscriber(session, config_a) as email_sub:
            async with SNSSubscriber(session, config_b) as analytics_sub:
                # Both subscribers receive this message
                await publisher.publish("user-events", Message(payload=b"new signup"))
```

### SNS+SQS IAM Permissions

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "sns:Publish",
        "sns:CreateTopic",
        "sns:Subscribe",
        "sns:ListTopics"
      ],
      "Resource": "arn:aws:sns:*:*:user-events"
    },
    {
      "Effect": "Allow",
      "Action": [
        "sqs:SendMessage",
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:ChangeMessageVisibility",
        "sqs:GetQueueUrl",
        "sqs:GetQueueAttributes",
        "sqs:CreateQueue",
        "sqs:SetQueueAttributes"
      ],
      "Resource": "arn:aws:sqs:*:*:user-events-*"
    }
  ]
}
```

Remove `sns:CreateTopic`, `sns:Subscribe`, `sqs:CreateQueue`, `sqs:SetQueueAttributes` if `create_resources=False`.

## Configuration

```python
SQSConfig(
    wait_time_s=20,            # Long polling (max 20)
    visibility_timeout_s=30,   # Redelivery timeout
    max_messages=10,           # Messages per poll (max 10)
    create_queue_if_missing=True,
)

SNSConfig(
    consumer_group="my-service",  # Queue name: {topic}-{consumer_group}
    create_resources=True,        # Auto-create topic, queue, subscription
    sqs_config=SQSConfig(),       # SQS settings for the subscriber
)
```

## Localstack Testing

```python
async with SQSPublisher(
    session,
    endpoint_url="http://localhost:4566",
) as publisher:
    ...
```

## With CQRS

```python
from natricine.cqrs import CommandBus, PydanticMarshaler

command_bus = CommandBus(
    publisher=SQSPublisher(session),
    subscriber=SQSSubscriber(session, SQSConfig()),
    marshaler=PydanticMarshaler(),
)
```
