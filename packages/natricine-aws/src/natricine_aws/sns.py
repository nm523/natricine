"""SNS Publisher and Subscriber implementations."""

import json
from collections.abc import AsyncIterator, Callable
from typing import TYPE_CHECKING

import aioboto3

from natricine.pubsub import Message
from natricine_aws.config import SNSConfig
from natricine_aws.marshaling import (
    encode_message_body,
    from_sns_sqs_message,
    to_message_attributes,
)

if TYPE_CHECKING:
    from types_aiobotocore_sns import SNSClient
    from types_aiobotocore_sqs import SQSClient


class SNSPublisher:
    """Publisher that sends messages to SNS topics."""

    def __init__(
        self,
        session: aioboto3.Session,
        topic_arn_resolver: Callable[[str], str] | None = None,
        create_topic_if_missing: bool = True,
        endpoint_url: str | None = None,
        region_name: str = "us-east-1",
    ) -> None:
        """Initialize the SNS publisher.

        Args:
            session: aioboto3 Session for creating clients.
            topic_arn_resolver: Optional function to resolve topic name to ARN.
                If not provided, topic is treated as topic name and resolved via API.
            create_topic_if_missing: Auto-create topic if it doesn't exist.
            endpoint_url: Optional endpoint URL (for localstack).
            region_name: AWS region name.
        """
        self._session = session
        self._topic_arn_resolver = topic_arn_resolver
        self._create_topic_if_missing = create_topic_if_missing
        self._endpoint_url = endpoint_url
        self._region_name = region_name
        self._closed = False
        self._topic_arns: dict[str, str] = {}
        self._client: "SNSClient | None" = None

    async def _get_client(self) -> "SNSClient":
        """Get or create the SNS client."""
        if self._client is None:
            self._client = await self._session.client(
                "sns",
                endpoint_url=self._endpoint_url,
                region_name=self._region_name,
            ).__aenter__()
        return self._client

    async def _get_topic_arn(self, topic: str) -> str:
        """Resolve topic name to ARN, creating topic if needed."""
        if topic in self._topic_arns:
            return self._topic_arns[topic]

        if self._topic_arn_resolver:
            arn = self._topic_arn_resolver(topic)
            self._topic_arns[topic] = arn
            return arn

        client = await self._get_client()

        # SNS create_topic is idempotent - returns existing topic if it exists
        if self._create_topic_if_missing:
            response = await client.create_topic(Name=topic)
            arn = response["TopicArn"]
            self._topic_arns[topic] = arn
            return arn

        # List topics to find the ARN (no direct get_topic API)
        paginator = client.get_paginator("list_topics")
        async for page in paginator.paginate():
            for topic_info in page.get("Topics", []):
                topic_arn = topic_info["TopicArn"]
                # ARN format: arn:aws:sns:region:account:topic-name
                if topic_arn.endswith(f":{topic}"):
                    self._topic_arns[topic] = topic_arn
                    return topic_arn

        msg = f"Topic {topic} not found"
        raise ValueError(msg)

    async def publish(self, topic: str, *messages: Message) -> None:
        """Publish messages to an SNS topic."""
        if self._closed:
            msg = "Publisher is closed"
            raise RuntimeError(msg)

        client = await self._get_client()
        topic_arn = await self._get_topic_arn(topic)

        for message in messages:
            # Convert message attributes to SNS format
            sqs_attrs = to_message_attributes(message)
            sns_attrs = {
                k: {"DataType": v["DataType"], "StringValue": v["StringValue"]}
                for k, v in sqs_attrs.items()
            }

            await client.publish(
                TopicArn=topic_arn,
                Message=encode_message_body(message.payload),
                MessageAttributes=sns_attrs,
            )

    async def close(self) -> None:
        """Close the publisher."""
        self._closed = True
        if self._client:
            await self._client.__aexit__(None, None, None)
            self._client = None

    async def __aenter__(self) -> "SNSPublisher":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        await self.close()


class SNSSubscriber:
    """Subscriber that receives SNS messages via an auto-created SQS queue."""

    def __init__(
        self,
        session: aioboto3.Session,
        config: SNSConfig | None = None,
        topic_arn_resolver: Callable[[str], str] | None = None,
        endpoint_url: str | None = None,
        region_name: str = "us-east-1",
    ) -> None:
        """Initialize the SNS subscriber.

        Args:
            session: aioboto3 Session for creating clients.
            config: SNS configuration.
            topic_arn_resolver: Optional function to resolve topic name to ARN.
            endpoint_url: Optional endpoint URL (for localstack).
            region_name: AWS region name.
        """
        self._session = session
        self._config = config or SNSConfig()
        self._topic_arn_resolver = topic_arn_resolver
        self._endpoint_url = endpoint_url
        self._region_name = region_name
        self._closed = False
        self._sns_client: "SNSClient | None" = None
        self._sqs_client: "SQSClient | None" = None
        # topic -> (queue_url, queue_arn)
        self._setup_complete: dict[str, tuple[str, str]] = {}

    async def _get_sns_client(self) -> "SNSClient":
        """Get or create the SNS client."""
        if self._sns_client is None:
            self._sns_client = await self._session.client(
                "sns",
                endpoint_url=self._endpoint_url,
                region_name=self._region_name,
            ).__aenter__()
        return self._sns_client

    async def _get_sqs_client(self) -> "SQSClient":
        """Get or create the SQS client."""
        if self._sqs_client is None:
            self._sqs_client = await self._session.client(
                "sqs",
                endpoint_url=self._endpoint_url,
                region_name=self._region_name,
            ).__aenter__()
        return self._sqs_client

    async def _get_topic_arn(self, topic: str) -> str:
        """Resolve topic name to ARN."""
        if self._topic_arn_resolver:
            return self._topic_arn_resolver(topic)

        sns = await self._get_sns_client()

        if self._config.create_resources:
            response = await sns.create_topic(Name=topic)
            return response["TopicArn"]

        # Search for existing topic
        paginator = sns.get_paginator("list_topics")
        async for page in paginator.paginate():
            for topic_info in page.get("Topics", []):
                topic_arn = topic_info["TopicArn"]
                if topic_arn.endswith(f":{topic}"):
                    return topic_arn

        msg = f"Topic {topic} not found"
        raise ValueError(msg)

    async def _setup_subscription(self, topic: str) -> tuple[str, str]:
        """Set up SQS queue and SNS subscription.

        Returns (queue_url, queue_arn).
        """
        if topic in self._setup_complete:
            return self._setup_complete[topic]

        sns = await self._get_sns_client()
        sqs = await self._get_sqs_client()

        # Get/create SNS topic
        topic_arn = await self._get_topic_arn(topic)

        # Create SQS queue for this consumer group
        queue_name = f"{topic}-{self._config.consumer_group}"
        queue_response = await sqs.create_queue(QueueName=queue_name)
        queue_url = queue_response["QueueUrl"]

        # Get queue ARN
        attrs_response = await sqs.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=["QueueArn"],
        )
        queue_arn = attrs_response["Attributes"]["QueueArn"]

        # Set queue policy to allow SNS to send messages
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "sns.amazonaws.com"},
                    "Action": "sqs:SendMessage",
                    "Resource": queue_arn,
                    "Condition": {"ArnEquals": {"aws:SourceArn": topic_arn}},
                }
            ],
        }
        await sqs.set_queue_attributes(
            QueueUrl=queue_url,
            Attributes={"Policy": json.dumps(policy)},
        )

        # Subscribe queue to topic
        await sns.subscribe(
            TopicArn=topic_arn,
            Protocol="sqs",
            Endpoint=queue_arn,
            # We want SNS envelope for attributes
            Attributes={"RawMessageDelivery": "false"},
        )

        self._setup_complete[topic] = (queue_url, queue_arn)
        return queue_url, queue_arn

    def subscribe(self, topic: str) -> AsyncIterator[Message]:
        """Subscribe to an SNS topic via SQS."""
        if self._closed:
            msg = "Subscriber is closed"
            raise RuntimeError(msg)

        return self._subscribe_iter(topic)

    async def _subscribe_iter(self, topic: str) -> AsyncIterator[Message]:
        """Poll messages from the SQS queue."""
        sqs = await self._get_sqs_client()
        queue_url, _ = await self._setup_subscription(topic)

        sqs_config = self._config.sqs_config

        while not self._closed:
            response = await sqs.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=sqs_config.max_messages,
                WaitTimeSeconds=sqs_config.wait_time_s,
                VisibilityTimeout=sqs_config.visibility_timeout_s,
                MessageAttributeNames=["All"],
            )

            messages = response.get("Messages", [])
            if not messages:
                continue

            for sqs_msg in messages:
                receipt_handle = sqs_msg.get("ReceiptHandle", "")

                async def make_ack(rh: str = receipt_handle) -> None:
                    await sqs.delete_message(
                        QueueUrl=queue_url,
                        ReceiptHandle=rh,
                    )

                async def make_nack(rh: str = receipt_handle) -> None:
                    await sqs.change_message_visibility(
                        QueueUrl=queue_url,
                        ReceiptHandle=rh,
                        VisibilityTimeout=0,
                    )

                # Use SNS-aware unmarshaling to unwrap envelope
                message = from_sns_sqs_message(
                    sqs_msg,
                    ack_func=make_ack,
                    nack_func=make_nack,
                )
                yield message

    async def close(self) -> None:
        """Close the subscriber."""
        self._closed = True
        if self._sns_client:
            await self._sns_client.__aexit__(None, None, None)
            self._sns_client = None
        if self._sqs_client:
            await self._sqs_client.__aexit__(None, None, None)
            self._sqs_client = None

    async def __aenter__(self) -> "SNSSubscriber":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        await self.close()
