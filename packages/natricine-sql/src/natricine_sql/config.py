"""Configuration dataclass for SQL pub/sub."""

from dataclasses import dataclass


@dataclass
class SQLConfig:
    """Configuration for SQL publisher/subscriber."""

    consumer_group: str = "default"
    """Consumer group name for competing consumers."""

    poll_interval: float = 1.0
    """Seconds between poll attempts when no messages found."""

    ack_deadline: float = 30.0
    """Seconds before unclaimed message is redelivered (visibility timeout)."""

    batch_size: int = 10
    """Maximum messages to fetch per poll."""

    table_prefix: str = "natricine_"
    """Prefix for table names. Topic 'orders' becomes 'natricine_orders'."""

    auto_create_tables: bool = True
    """Automatically create tables if they don't exist."""
