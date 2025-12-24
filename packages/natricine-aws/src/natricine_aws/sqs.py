"""SQS Publisher and Subscriber implementations."""

from collections.abc import AsyncIterator, Callable
from typing import TYPE_CHECKING

import aioboto3

from natricine.pubsub import Message
from natricine_aws.config import SQSConfig
from natricine_aws.marshaling import (
    encode_message_body,
    from_sqs_message,
    to_message_attributes,
)

if TYPE_CHECKING:
    from types_aiobotocore_sqs import SQSClient


class SQSPublisher:
    """Publisher that sends messages to SQS queues."""

    def __init__(
        self,
        session: aioboto3.Session,
        config: SQSConfig | None = None,
        queue_url_resolver: Callable[[str], str] | None = None,
        endpoint_url: str | None = None,
        region_name: str = "us-east-1",
    ) -> None:
        """Initialize the SQS publisher.

        Args:
            session: aioboto3 Session for creating clients.
            config: SQS configuration.
            queue_url_resolver: Optional function to resolve topic to queue URL.
                If not provided, topic is treated as queue name and resolved via API.
            endpoint_url: Optional endpoint URL (for localstack).
            region_name: AWS region name.
        """
        self._session = session
        self._config = config or SQSConfig()
        self._queue_url_resolver = queue_url_resolver
        self._endpoint_url = endpoint_url
        self._region_name = region_name
        self._closed = False
        self._queue_urls: dict[str, str] = {}
        self._client: "SQSClient | None" = None

    async def _get_client(self) -> "SQSClient":
        """Get or create the SQS client."""
        if self._client is None:
            self._client = await self._session.client(
                "sqs",
                endpoint_url=self._endpoint_url,
                region_name=self._region_name,
            ).__aenter__()
        return self._client

    async def _get_queue_url(self, topic: str) -> str:
        """Resolve topic to queue URL, creating queue if needed."""
        if topic in self._queue_urls:
            return self._queue_urls[topic]

        if self._queue_url_resolver:
            url = self._queue_url_resolver(topic)
            self._queue_urls[topic] = url
            return url

        client = await self._get_client()

        # Try to get existing queue
        try:
            response = await client.get_queue_url(QueueName=topic)
            url = response["QueueUrl"]
            self._queue_urls[topic] = url
            return url
        except client.exceptions.QueueDoesNotExist:
            if not self._config.create_queue_if_missing:
                raise

        # Create queue
        response = await client.create_queue(QueueName=topic)
        url = response["QueueUrl"]
        self._queue_urls[topic] = url
        return url

    async def publish(self, topic: str, *messages: Message) -> None:
        """Publish messages to an SQS queue."""
        if self._closed:
            msg = "Publisher is closed"
            raise RuntimeError(msg)

        client = await self._get_client()
        queue_url = await self._get_queue_url(topic)

        for message in messages:
            await client.send_message(
                QueueUrl=queue_url,
                MessageBody=encode_message_body(message.payload),
                MessageAttributes=to_message_attributes(message),
            )

    async def close(self) -> None:
        """Close the publisher."""
        self._closed = True
        if self._client:
            await self._client.__aexit__(None, None, None)
            self._client = None

    async def __aenter__(self) -> "SQSPublisher":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        await self.close()


class SQSSubscriber:
    """Subscriber that polls messages from SQS queues."""

    def __init__(
        self,
        session: aioboto3.Session,
        config: SQSConfig | None = None,
        queue_url_resolver: Callable[[str], str] | None = None,
        endpoint_url: str | None = None,
        region_name: str = "us-east-1",
    ) -> None:
        """Initialize the SQS subscriber.

        Args:
            session: aioboto3 Session for creating clients.
            config: SQS configuration.
            queue_url_resolver: Optional function to resolve topic to queue URL.
            endpoint_url: Optional endpoint URL (for localstack).
            region_name: AWS region name.
        """
        self._session = session
        self._config = config or SQSConfig()
        self._queue_url_resolver = queue_url_resolver
        self._endpoint_url = endpoint_url
        self._region_name = region_name
        self._closed = False
        self._queue_urls: dict[str, str] = {}
        self._client: "SQSClient | None" = None

    async def _get_client(self) -> "SQSClient":
        """Get or create the SQS client."""
        if self._client is None:
            self._client = await self._session.client(
                "sqs",
                endpoint_url=self._endpoint_url,
                region_name=self._region_name,
            ).__aenter__()
        return self._client

    async def _get_queue_url(self, topic: str) -> str:
        """Resolve topic to queue URL, creating queue if needed."""
        if topic in self._queue_urls:
            return self._queue_urls[topic]

        if self._queue_url_resolver:
            url = self._queue_url_resolver(topic)
            self._queue_urls[topic] = url
            return url

        client = await self._get_client()

        # Try to get existing queue
        try:
            response = await client.get_queue_url(QueueName=topic)
            url = response["QueueUrl"]
            self._queue_urls[topic] = url
            return url
        except client.exceptions.QueueDoesNotExist:
            if not self._config.create_queue_if_missing:
                raise

        # Create queue
        response = await client.create_queue(QueueName=topic)
        url = response["QueueUrl"]
        self._queue_urls[topic] = url
        return url

    def subscribe(self, topic: str) -> AsyncIterator[Message]:
        """Subscribe to an SQS queue."""
        if self._closed:
            msg = "Subscriber is closed"
            raise RuntimeError(msg)

        return self._subscribe_iter(topic)

    async def _subscribe_iter(self, topic: str) -> AsyncIterator[Message]:
        """Poll messages from the queue."""
        client = await self._get_client()
        queue_url = await self._get_queue_url(topic)

        while not self._closed:
            response = await client.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=self._config.max_messages,
                WaitTimeSeconds=self._config.wait_time_s,
                VisibilityTimeout=self._config.visibility_timeout_s,
                MessageAttributeNames=["All"],
            )

            messages = response.get("Messages", [])
            if not messages:
                continue

            for sqs_msg in messages:
                receipt_handle = sqs_msg.get("ReceiptHandle", "")

                async def make_ack(rh: str = receipt_handle) -> None:
                    await client.delete_message(
                        QueueUrl=queue_url,
                        ReceiptHandle=rh,
                    )

                async def make_nack(rh: str = receipt_handle) -> None:
                    # Set visibility to 0 for immediate redelivery
                    await client.change_message_visibility(
                        QueueUrl=queue_url,
                        ReceiptHandle=rh,
                        VisibilityTimeout=0,
                    )

                message = from_sqs_message(
                    sqs_msg,
                    ack_func=make_ack,
                    nack_func=make_nack,
                )
                yield message

    async def close(self) -> None:
        """Close the subscriber."""
        self._closed = True
        if self._client:
            await self._client.__aexit__(None, None, None)
            self._client = None

    async def __aenter__(self) -> "SQSSubscriber":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        await self.close()
