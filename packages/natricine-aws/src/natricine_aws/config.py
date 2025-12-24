"""Configuration dataclasses for AWS pub/sub."""

from dataclasses import dataclass, field


@dataclass
class SQSConfig:
    """Configuration for SQS publisher/subscriber."""

    wait_time_s: int = 20
    """Long polling wait time (max 20s)."""

    visibility_timeout_s: int = 30
    """Time before message is redelivered if not acknowledged."""

    max_messages: int = 10
    """Messages to fetch per poll (max 10)."""

    create_queue_if_missing: bool = True
    """Auto-create queue if it doesn't exist."""


@dataclass
class SNSConfig:
    """Configuration for SNS publisher/subscriber."""

    consumer_group: str = "default"
    """Used in SQS queue name for fan-out: {topic}-{consumer_group}."""

    create_resources: bool = True
    """Auto-create SNS topic, SQS queue, and subscription."""

    sqs_config: SQSConfig = field(default_factory=SQSConfig)
    """Configuration for the underlying SQS subscriber."""
