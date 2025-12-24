"""HTTP message marshaling utilities.

Compatible with watermill-http default format.
"""

import json
from collections.abc import Mapping
from uuid import UUID, uuid4

# Default header names - matches watermill-http
DEFAULT_UUID_HEADER = "Message-Uuid"
DEFAULT_METADATA_HEADER = "Message-Metadata"


def extract_metadata(
    headers: Mapping[str, str],
    metadata_header: str = DEFAULT_METADATA_HEADER,
) -> dict[str, str]:
    """Extract metadata from HTTP headers.

    Metadata is stored as a JSON object in a single header (watermill-compatible).
    """
    for key, value in headers.items():
        if key.lower() == metadata_header.lower():
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return {}
    return {}


def extract_uuid(
    headers: Mapping[str, str],
    uuid_header: str = DEFAULT_UUID_HEADER,
) -> UUID:
    """Extract message UUID from HTTP headers.

    Falls back to generating a new UUID if not present.
    """
    for key, value in headers.items():
        if key.lower() == uuid_header.lower():
            return UUID(value)
    return uuid4()


def metadata_to_header(metadata: dict[str, str]) -> str:
    """Convert metadata dict to JSON string for header."""
    return json.dumps(metadata) if metadata else "{}"
