"""Configuration for HTTP pub/sub."""

from dataclasses import dataclass, field

from natricine_http.marshaling import DEFAULT_METADATA_HEADER, DEFAULT_UUID_HEADER


@dataclass
class HTTPPublisherConfig:
    """Configuration for HTTPPublisher.

    Attributes:
        base_url: Base URL for HTTP requests (e.g., "http://api.example.com")
        topic_path: URL path pattern with {topic} placeholder (default: "/{topic}")
        timeout_s: Request timeout in seconds
        headers: Default headers to include in all requests
        uuid_header: Header name for message UUID
        metadata_header: Header name for message metadata JSON
    """

    base_url: str
    topic_path: str = "/{topic}"
    timeout_s: float = 30.0
    headers: dict[str, str] = field(default_factory=dict)
    uuid_header: str = DEFAULT_UUID_HEADER
    metadata_header: str = DEFAULT_METADATA_HEADER


@dataclass
class HTTPSubscriberConfig:
    """Configuration for HTTPSubscriber.

    Attributes:
        uuid_header: Header name for message UUID
        metadata_header: Header name for message metadata JSON
    """

    uuid_header: str = DEFAULT_UUID_HEADER
    metadata_header: str = DEFAULT_METADATA_HEADER
