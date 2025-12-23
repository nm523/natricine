"""Configuration for HTTP pub/sub."""

from dataclasses import dataclass, field


@dataclass
class HTTPPublisherConfig:
    """Configuration for HTTPPublisher.

    Attributes:
        base_url: Base URL for HTTP requests (e.g., "http://api.example.com")
        topic_path: URL path pattern with {topic} placeholder (default: "/{topic}")
        timeout_s: Request timeout in seconds
        headers: Default headers to include in all requests
    """

    base_url: str
    topic_path: str = "/{topic}"
    timeout_s: float = 30.0
    headers: dict[str, str] = field(default_factory=dict)
